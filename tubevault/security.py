import hashlib
import secrets
import time
from collections import defaultdict
from fastapi import HTTPException, Request


class Security:
    def __init__(self, password, origins):
        self.password = hashlib.sha256(password.encode()).digest()
        self.sessions = {}
        self.failures = defaultdict(list)
        self.origins = set(origins.split(","))

    def login(self, request, password):
        key = request.client.host
        now = time.time()
        self.failures[key] = [t for t in self.failures[key] if t > now - 300]
        if len(self.failures[key]) >= 10:
            raise HTTPException(429, "Too many attempts; wait five minutes")
        if not secrets.compare_digest(self.password, hashlib.sha256(password.encode()).digest()):
            self.failures[key].append(now)
            raise HTTPException(401, "Invalid password")
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.sessions = {k: v for k, v in self.sessions.items() if v[1] > now}
        self.sessions[token] = (csrf, now + 12 * 3600)
        return token, csrf

    def check(self, request: Request):
        session = self.sessions.get(request.cookies.get("tv_session", ""))
        if not session or session[1] < time.time():
            raise HTTPException(401, "Sign in required")
        if request.method not in {"GET", "HEAD"}:
            if request.headers.get("origin") not in self.origins:
                raise HTTPException(403, "Origin rejected")
            if not secrets.compare_digest(request.headers.get("x-csrf-token", ""), session[0]):
                raise HTTPException(403, "CSRF rejected")
        return session[0]
