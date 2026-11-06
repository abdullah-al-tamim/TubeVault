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
        assert client.post('/api/queue/bulk',json={'ids':['missing'],'action':'pause'},headers=headers).json()['results'][0]['ok'] is False
        assert client.post('/api/queue/add-files',json={'paths':['missing.mp4']},headers=headers).status_code == 200
        assert client.put('/api/queue/concurrency',json={'concurrency':4},headers=headers).status_code == 200
        assert db.settings()['concurrency'] == 4
        assert client.put('/api/queue/concurrency',json={'concurrency':359},headers=headers).status_code == 422


def test_legacy_vault_migration_preserves_db_and_protected_credentials(db,tmp_path):
    from tubevault.desktop_data import migrate_legacy
    from tubevault.db import Database
    source=tmp_path/'legacy';source.mkdir()
    import sqlite3
    with sqlite3.connect(tmp_path/'test.db') as old,sqlite3.connect(source/'tubevault.db') as new:old.backup(new)
    (source/'inbox').mkdir();(source/'inbox'/'part.bin').write_bytes(b'preserved')
    target=tmp_path/'stable'/'data'
    stores={source:MemorySecrets(),target:MemorySecrets()}
    stores[source].set('google','test-only-protected-token')
    migrate_legacy(source,target,lambda p:stores[p])
    assert stores[target].get('google')=='test-only-protected-token'
    assert (target/'inbox'/'part.bin').read_bytes()==b'preserved'
    assert (source/'tubevault.db').exists()
    assert (target/'tubevault.db').exists()
    migrate_legacy(source,target,lambda p:stores[p])
