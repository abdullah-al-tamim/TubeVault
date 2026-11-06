"""First-run setup and validated Desktop OAuth client import."""
import json
import re
from .db import Account, Watch
from sqlalchemy import select


def validate_client(document):
    if not isinstance(document, dict) or not isinstance(document.get('installed'), dict):
        raise ValueError('Choose the JSON downloaded for a Desktop app OAuth client, not a Web client or service account.')
    client = document['installed']
    if not re.fullmatch(r'[A-Za-z0-9._-]+\.apps\.googleusercontent\.com', str(client.get('client_id', ''))):
        raise ValueError('Invalid Google Desktop client ID')
    if not isinstance(client.get('client_secret'), str) or not 5 <= len(client['client_secret']) <= 512:
        raise ValueError('The Desktop client secret is missing')
    if client.get('auth_uri') != 'https://accounts.google.com/o/oauth2/auth' or client.get('token_uri') != 'https://oauth2.googleapis.com/token':
        raise ValueError('Only official Google authorization and token endpoints are accepted')
    # Store only fields required by the installed-app flow.
    return {'installed': {k: client[k] for k in ('client_id', 'client_secret', 'auth_uri', 'token_uri')}}


class SetupService:
    def __init__(self, db, auth, desktop=None):
        self.db, self.auth, self.desktop = db, auth, desktop

    def status(self):
        settings = self.db.settings()
        with self.db.session() as s:
            account = s.scalar(select(Account))
            watches = list(s.scalars(select(Watch).where(Watch.enabled == True)))
        return dict(completed=settings.get('onboarding_completed', False),
                    credentials_ready=self.auth.client_ready(), connected=self.auth.connected(),
                    account={'id': account.id, 'name': account.name} if account else None,
                    watch_count=len(watches), desktop=self.desktop is not None,
                    startup_enabled=self.desktop.startup_enabled() if self.desktop else False,
                    preferred_email=settings.get('preferred_email', ''),
                    expected_channel=settings.get('expected_channel', ''),
                    automatic=settings.get('mode') == 'automatic' and not settings.get('paused'))

    def import_client(self, document):
        client = validate_client(document)
        self.auth.secrets.set('oauth-client', json.dumps(client))
        return {'ok': True}
