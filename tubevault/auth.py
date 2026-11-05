import json
import threading
import keyring
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from .db import Account

SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl"


class Secrets:
    def __init__(self):
        # Fail closed: do not silently use a plaintext third-party keyring backend.
        if "Windows" not in type(keyring.get_keyring()).__module__:
            raise RuntimeError("TubeVault requires Windows Credential Manager")

    def get(self, key):
        return keyring.get_password("TubeVault", key)

    def set(self, key, value):
        keyring.set_password("TubeVault", key, value)

    def delete(self, key):
        if self.get(key):
            keyring.delete_password("TubeVault", key)


class Auth:
    def __init__(self, db, secrets, config):
        self.db, self.secrets, self.config = db, secrets, config
        self.lock = threading.Lock()
        self.connect_lock = threading.Lock()

    def token(self):
        with self.lock:
            raw = self.secrets.get("google")
            if not raw:
                raise RuntimeError("Connect a YouTube channel in Settings")
            credentials = Credentials.from_authorized_user_info(json.loads(raw), [SCOPE])
            if not credentials.valid:
                credentials.refresh(Request())
                self.secrets.set("google", credentials.to_json())
            return credentials.token

    def connect(self):
        if not self.connect_lock.acquire(blocking=False):
            raise RuntimeError("Connection already in progress")
        try:
            flow = InstalledAppFlow.from_client_secrets_file(str(self.config.client_secret), [SCOPE], autogenerate_code_verifier=True)
            credentials = flow.run_local_server(host="127.0.0.1", port=0, timeout_seconds=180,
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
