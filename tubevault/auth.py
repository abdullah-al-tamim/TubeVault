import json
import logging
import hashlib
import threading
import keyring
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from .db import Account

SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"


class Secrets:
    def __init__(self, data_dir=None):
        # Fail closed: do not silently use a plaintext third-party keyring backend.
        if "Windows" not in type(keyring.get_keyring()).__module__:
            raise RuntimeError("TubeVault requires Windows Credential Manager")
        from .config import config
        self.service = "TubeVault-" + hashlib.sha256(str((data_dir or config.data_dir).resolve()).encode()).hexdigest()[:16]

    def get(self, key):
        return keyring.get_password(f"{self.service}-{key}", key) or keyring.get_password(self.service, key)

    def set(self, key, value):
        keyring.set_password(f"{self.service}-{key}", key, value)

    def delete(self, key):
        for service in (f"{self.service}-{key}", self.service):
            if keyring.get_password(service, key):
                keyring.delete_password(service, key)


class Auth:
    def __init__(self, db, secrets, config):
        self.db, self.secrets, self.config = db, secrets, config
        self.lock = threading.Lock()
        self.connect_lock = threading.Lock()

    def connected(self):
        return bool(self.secrets.get("google"))

    def client_ready(self):
        return bool(self.secrets.get('oauth-client')) or self.config.client_secret.is_file()

    def client_config(self):
        from .setup_service import validate_client
        stored = self.secrets.get('oauth-client')
        if stored:
            return validate_client(json.loads(stored))
        if self.config.client_secret.is_file():
            return validate_client(json.loads(self.config.client_secret.read_text(encoding='utf-8-sig')))
        raise ValueError('Import your Desktop OAuth JSON using the Google setup guide first.')

    def token(self):
        with self.lock:
            raw = self.secrets.get("google")
            if not raw:
                from .youtube import APIError
                raise APIError("Google sign-in required; connect in Settings", retryable=True)
            credentials = Credentials.from_authorized_user_info(json.loads(raw), [SCOPE])
            if not credentials.valid:
                credentials.refresh(Request())
                self.secrets.set("google", credentials.to_json())
            return credentials.token

    def connect(self):
        if not self.connect_lock.acquire(blocking=False):
            raise RuntimeError("Connection already in progress")
        try:
            logging.getLogger("google_auth_oauthlib.flow").disabled = True
            flow = InstalledAppFlow.from_client_config(self.client_config(), [SCOPE], autogenerate_code_verifier=True)
            settings = self.db.settings()
            credentials = flow.run_local_server(host="127.0.0.1", port=0, timeout_seconds=180,
                                              login_hint=settings.get('preferred_email', ''), prompt='consent',
                                              authorization_prompt_message="Complete authorization in your browser.",
                                              success_message="TubeVault connected. You may close this window.")
            import httpx
            response = httpx.get("https://www.googleapis.com/youtube/v3/channels", params={"part": "snippet", "mine": "true"},
                                 headers={"Authorization": f"Bearer {credentials.token}"}, timeout=30)
            response.raise_for_status()
            channel = response.json()["items"][0]
            with self.db.session() as s:
                from sqlalchemy import select
                old = s.scalar(select(Account))
                if old and old.id != channel["id"]:
                    raise RuntimeError("Different channel: use a separate TubeVault data directory")
                s.merge(Account(id=channel["id"], name=channel["snippet"]["title"]))
            self.secrets.set("google", credentials.to_json())
        finally:
            self.connect_lock.release()

    def disconnect(self):
        self.db.configure({"paused": True})
        with self.lock:
            self.secrets.delete("google")
