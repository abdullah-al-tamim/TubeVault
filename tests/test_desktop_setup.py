import json
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from tubevault.api import create_app
from tubevault.config import Config
from tubevault.desktop import DesktopHost
from tubevault.setup_service import validate_client


class MemorySecrets:
    def __init__(self):
        self.data = {}
    def get(self, key):
        return self.data.get(key)
    def set(self, key, value):
        self.data[key] = value


def client_document():
    return {'installed': {'client_id':'123-test.apps.googleusercontent.com', 'client_secret':'test-only-secret',
        'auth_uri':'https://accounts.google.com/o/oauth2/auth', 'token_uri':'https://oauth2.googleapis.com/token'}}


def test_rejects_service_accounts_and_token_endpoint_substitution():
    with pytest.raises(ValueError):
        validate_client({'type':'service_account'})
    document = client_document()
    document['installed']['token_uri'] = 'https://attacker.example/token'
    with pytest.raises(ValueError):
        validate_client(document)


def test_desktop_ticket_is_single_use(tmp_path):
    host = DesktopHost(tmp_path, MemorySecrets())
    ticket = host.ticket()
    assert host.consume_ticket(ticket)
    assert not host.consume_ticket(ticket)
    assert not host.consume_ticket('guessed')


def test_protected_desktop_setup_and_client_import(db, tmp_path):
    auth = Mock()
    auth.connected.return_value = False
    auth.client_ready.return_value = False
    auth.secrets = MemorySecrets()
    host = DesktopHost(tmp_path, auth.secrets)
    host.startup_enabled = Mock(return_value=False)
    host.set_startup = Mock()
    config = Config(data_dir=tmp_path, password='generated-local-password', allowed_hosts='testserver', origins='http://testserver')
    app = create_app(config, db, (auth,Mock(),Mock(),Mock()), background=False, desktop=host)
    with TestClient(app) as client:
        assert client.get('/api/setup/status').status_code == 401
        ticket = host.ticket()
        assert client.post('/api/desktop/session',json={'ticket':ticket},headers={'Origin':'https://evil.example'}).status_code == 403
        result = client.post('/api/desktop/session',json={'ticket':ticket},headers={'Origin':'http://testserver'})
        assert result.status_code == 200
        assert client.post('/api/desktop/session',json={'ticket':ticket},headers={'Origin':'http://testserver'}).status_code == 401
        headers = {'Origin':'http://testserver','X-CSRF-Token':result.json()['csrf']}
        assert client.put('/api/setup/client',json=client_document(),headers=headers).json() == {'ok':True}
        assert json.loads(auth.secrets.get('oauth-client')) == client_document()
        status = client.get('/api/setup/status').json()
        assert 'client_secret' not in json.dumps(status)
        assert client.post('/api/setup/complete',json={'automatic':True},headers=headers).status_code == 409
        assert client.post('/api/setup/complete',json={'automatic':False,'startup':True},headers=headers).status_code == 200
        host.set_startup.assert_called_once_with(True)
        assert db.settings()['onboarding_completed'] is True
        assert db.settings()['paused'] is True
