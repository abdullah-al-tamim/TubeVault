"""Temporary, upload-only Wi-Fi receiver, separate from the localhost dashboard."""
import asyncio
import base64
import io
import ipaddress
import json
import secrets
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select

from .db import Transfer
from .imports import safe_name
from .paths import resource_root

PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in
                         ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
SESSION_SECONDS = 12 * 3600


def private_ipv4(value):
    address = ipaddress.ip_address(value)
    return any(address in network for network in PRIVATE_NETWORKS)


def lan_addresses():
    command = ("Get-NetIPAddress -AddressFamily IPv4 | "
               "Where-Object { $_.AddressState -eq 'Preferred' } | "
               "Select-Object IPAddress,InterfaceAlias | ConvertTo-Json -Compress")
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                            capture_output=True, text=True, timeout=15, creationflags=0x08000000)
    if result.returncode:
        raise ValueError("Windows could not list network connections")
    rows = json.loads(result.stdout or "[]")
    if isinstance(rows, dict):
        rows = [rows]
    return [{"address": row["IPAddress"], "name": row["InterfaceAlias"]}
            for row in rows if private_ipv4(row["IPAddress"])]


class PhoneFile(BaseModel):
    filename: str = Field(min_length=1, max_length=150)
    size: int = Field(gt=0, le=256_000_000_000)


class PairInput(BaseModel):
    invitation: str = Field(min_length=30, max_length=200)


class PhoneReceiver:
    def __init__(self, imports, scanner):
        self.imports, self.scanner = imports, scanner
        self.lock = threading.RLock()
        self.server = None
        self.thread = None
        self.listener = None
        self.url = ""
        self.collection = ""
        self.invitation = ""
        self.session = ""
        self.pair_deadline = 0
        self.deadline = 0
        self.transfers = set()
        self.progress = {}
        self.reserved_bytes = 0
        self.completed = 0
        self.paired = False
        self.timer = None

    def active(self):
        return self.server is not None and self.deadline > time.time()

    def status(self):
        with self.lock:
            return {"active": self.active(), "paired": self.paired,
                    "expires": self.deadline, "pair_expires": self.pair_deadline,
                    "collection": self.collection, "completed": self.completed}

    def start(self, address, collection):
        if not private_ipv4(address):
            raise ValueError("Choose your PC's private Wi-Fi or Ethernet address")
        safe_name(collection)
        if collection.startswith("."):
            raise ValueError("Choose a collection name without a leading dot")
        with self.lock:
            if self.active():
                raise ValueError("Stop the current receiving session before starting another")
            self.stop()
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                listener.bind((address, 0))
                listener.listen(8)
            except OSError:
                listener.close()
                raise ValueError("Could not open this network connection. Reconnect Wi-Fi and try again.") from None
            self.listener = listener
            self.url = f"http://{address}:{listener.getsockname()[1]}"
            self.collection = collection
            self.invitation = secrets.token_urlsafe(32)
            self.session = ""
            self.pair_deadline = time.time() + 600
            self.deadline = time.time() + SESSION_SECONDS
            self.transfers = set()
            self.progress = {}
            self.reserved_bytes = self.completed = 0
            self.paired = False
            import uvicorn
            server = uvicorn.Server(uvicorn.Config(
                self.create_app(address), access_log=False, log_config=None,
                limit_concurrency=8, timeout_keep_alive=5))
            self.server = server
            self.thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
            self.thread.start()
            for _ in range(100):
                if self.server.started:
                    break
                if not self.thread.is_alive():
                    self.stop()
                    raise ValueError("Phone receiver could not start")
                time.sleep(.02)
            if not self.server.started:
                self.stop()
                raise ValueError("Phone receiver took too long to start")
            self.timer = threading.Timer(SESSION_SECONDS, lambda: self.stop(server))
            self.timer.daemon = True
            self.timer.start()
            import qrcode
            pairing_url = self.url + "/#pair=" + self.invitation
            output = io.BytesIO()
            qrcode.make(pairing_url).save(output, format="PNG")
            return self.status() | {"url": pairing_url,
                "qr": "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")}

    def stop(self, expected_server=None):
        with self.lock:
            if expected_server is not None and self.server is not expected_server:
                return
            self.session = self.invitation = ""
            self.deadline = 0
            if self.timer:
                self.timer.cancel()
                self.timer = None
            if self.server:
                self.server.should_exit = True
                self.server = None
            if self.listener:
                # Uvicorn owns an active accept operation. Let its shutdown close
                # the socket to avoid Windows IOCP cancellation errors.
                if not self.thread or not self.thread.is_alive():
                    self.listener.close()
                self.listener = None

    def authorize(self, request):
        with self.lock:
            token = request.headers.get("authorization", "").removeprefix("Bearer ")
            if not self.active() or not self.session or not secrets.compare_digest(token, self.session):
                raise HTTPException(401, "Receiving session ended. Scan a new QR code on your PC.")
            if request.headers.get("origin") not in {None, self.url}:
                raise HTTPException(403, "Open the paired TubeVault page")

    def owned(self, transfer_id):
        if transfer_id not in self.transfers:
            raise HTTPException(404, "Transfer not found")

    def create_app(self, address):
        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=[address])

        @app.middleware("http")
        async def protect(request, call_next):
            length = request.headers.get("content-length", "0")
            if not length.isdigit() or int(length) > 4 * 1024 * 1024 + 4096:
                from fastapi import Response
                return Response("Request too large", status_code=413)
            response = await call_next(request)
            response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
                "Content-Security-Policy": "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'none'"})
            return response

        @app.post("/pair")
        def pair(body: PairInput, request: Request):
            with self.lock:
                if (not self.active() or self.paired or time.time() >= self.pair_deadline
                    or request.headers.get("origin") != self.url
                    or not secrets.compare_digest(body.invitation, self.invitation)):
                    raise HTTPException(401, "Pairing code expired or already used. Get a new code on the PC.")
                self.session = secrets.token_urlsafe(32)
                self.invitation = ""
                self.paired = True
                return {"token": self.session, "collection": self.collection}

        @app.get("/status")
        def status(request: Request):
            self.authorize(request)
            return self.status() | {"queue_paused": self.imports.db.settings()["paused"]}

        @app.post("/connection-test")
        async def connection_test(request: Request):
            self.authorize(request)
            received = 0
            started = time.monotonic()
            async for part in request.stream():
                received += len(part)
                if received > 1024 * 1024:
                    raise HTTPException(413, "Connection test too large")
            self.authorize(request)
            if received != 1024 * 1024:
                raise HTTPException(400, "Incomplete connection test")
            # Discard the sample: no file, queue entry or request contents logged.
            return {"bytes": received, "receive_seconds": time.monotonic() - started}

        @app.post("/files")
        def create_file(body: PhoneFile, request: Request):
            self.authorize(request)
            with self.lock:
                if len(self.transfers) >= 500 or self.reserved_bytes + body.size > 256_000_000_000:
                    raise HTTPException(409, "Session limit reached. Start a new receiving session on the PC.")
                if body.size + 1024**3 > shutil.disk_usage(self.imports.root).free:
                    raise HTTPException(409, "The PC needs more free disk space for this video")
                try:
                    transfer_id = self.imports.create(body.filename, self.collection, body.size)
                except ValueError as error:
                    raise HTTPException(400, str(error)) from None
                self.transfers.add(transfer_id)
                self.reserved_bytes += body.size
                return {"id": transfer_id}

        @app.get("/files/{transfer_id}")
        def file_status(transfer_id: str, request: Request):
            self.authorize(request)
            with self.lock:
                self.owned(transfer_id)
                progress = dict(self.progress.get(transfer_id, {}))
            with self.imports.db.session() as session:
                row = session.get(Transfer, transfer_id)
                return {"offset": row.offset, "state": row.state, "size": row.size,
                        "receiving": progress}

        @app.put("/files/{transfer_id}")
        async def chunk(transfer_id: str, offset: int, request: Request):
            self.authorize(request)
            with self.lock:
                self.owned(transfer_id)
                progress = {"chunk_offset": offset, "received": 0, "stage": "receiving"}
                self.progress[transfer_id] = progress
            data = bytearray()
            async for part in request.stream():
                data.extend(part)
                progress["received"] = len(data)
                if len(data) > 4 * 1024 * 1024:
                    raise HTTPException(413, "Transfer chunk too large")
            self.authorize(request)
            try:
                progress["stage"] = "saving"
                committed = await asyncio.to_thread(self.imports.append, transfer_id, offset, bytes(data))
                progress["stage"] = "saved"
                return {"offset": committed}
            except ValueError as error:
                raise HTTPException(409, str(error)) from None
            except OSError:
                raise HTTPException(409, "Could not save video. Check PC storage and try again.") from None

        @app.post("/files/{transfer_id}/finish")
        def finish(transfer_id: str, request: Request):
            self.authorize(request)
            with self.lock:
                self.owned(transfer_id)
            try:
                with self.imports.db.session() as session:
                    already = session.get(Transfer, transfer_id).state == "INGESTED"
                target = self.imports.finish(transfer_id)
                self.scanner.scan_import(target, self.imports.root)
            except ValueError as error:
                raise HTTPException(409, str(error)) from None
            except OSError:
                raise HTTPException(409, "Could not save video. Check PC storage and try again.") from None
            with self.lock:
                if not already:
                    self.completed += 1
            return {"saved": True, "queue_paused": self.imports.db.settings()["paused"]}

        @app.get("/{asset:path}")
        def page(asset: str):
            files = {"": ("index.html", "text/html"), "phone.js": ("phone.js", "text/javascript"),
                     "transfer-policy.js": ("transfer-policy.js", "text/javascript"),
                     "phone.css": ("phone.css", "text/css")}
            if asset not in files:
                raise HTTPException(404)
            filename, media_type = files[asset]
            return FileResponse(resource_root() / "phone" / filename, media_type=media_type)

        return app
