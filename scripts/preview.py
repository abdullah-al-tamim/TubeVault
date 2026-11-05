"""Dependency-free UI preview. Synthetic data only; no filesystem scanning or Google calls."""
import argparse
import copy
import json
import mimetypes
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "frontend" / "dist"
NOW = time.time()
COLLECTIONS = ["Bashgari to Dhaka", "Coxsbazar family", "Kuakata 26"]
SETTINGS = dict(paused=True, mode="manual", timezone="Asia/Dhaka", start_hour=0,
                end_hour=6, concurrency=1, bandwidth_kbps=0, pause_metered=True,
                privacy="private", title_template="{filename}", description_template="",
                sort="name", notifications=True, cooldown=0)


def sample_data():
    jobs = []
    for i, (title, state, size) in enumerate([
        ("DJI_0001.mp4", "COMPLETED", 2_800_000_000),
        ("DJI_0002.mp4", "COMPLETED", 1_700_000_000),
        ("Sunset at Coxsbazar.mov", "QUEUED", 4_200_000_000),
        ("Family moments.mp4", "QUEUED", 980_000_000),
        ("Kuakata morning.mp4", "FAILED_RETRYABLE", 3_100_000_000),
        ("Coastal road.mp4", "PAUSED", 2_300_000_000),
    ]):
        collection = COLLECTIONS[i // 2]
        jobs.append(dict(id=f"sample-{i}", title=title, state=state, size=size,
            progress=size if state == "COMPLETED" else 0, speed=0, playlist=collection,
            privacy="private", retries=1 if state == "FAILED_RETRYABLE" else 0,
            video_id=None, error="Sample network interruption" if state == "FAILED_RETRYABLE" else "",
            sha256=(str(i + 1) * 64), path=f"D:\\ACTION Camera\\{collection}\\{title}",
            created=NOW-i*3600, description="Sample footage — preview only", tags=["travel"], made_for_kids=False))
    return dict(preview=True, jobs=jobs,
        watches=[dict(id="sample-watch", path="D:\\ACTION Camera", enabled=True,
                      automatic=True, depth=8, stability=60, unsorted=True,
                      privacy="private", excludes=["*.tmp"], max_bytes=256_000_000_000)],
        mappings=[dict(id=f"collection-{i}", path=f"D:\\ACTION Camera\\{title}", title=title,
                       privacy="private", playlist_id=None) for i, title in enumerate(COLLECTIONS)],
        instances=[dict(id=j["id"], path=j["path"], size=j["size"], reason="QUEUED") for j in jobs],
        events=[dict(id="sample-event-1", at=NOW-120, message="Sample: DJI_0002.mp4 archived successfully"),
                dict(id="sample-event-2", at=NOW-300, message="Sample: discovered 6 videos in ACTION Camera")],
        imports=[dict(id="sample-import", filename="Beach walk.MOV", collection="Coxsbazar family",
                      size=750_000_000, offset=750_000_000, state="INGESTED")],
        account=None, settings=copy.deepcopy(SETTINGS))


class PreviewServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, port):
        super().__init__(("127.0.0.1", port), PreviewHandler)
        self.data = sample_data()
        self.lock = threading.Lock()


class PreviewHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, value, status=200):
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/session":
            return self.reply({"csrf": "sample-preview-only"})
        if path in {"/api/snapshot", "/api/events"}:
            with self.server.lock:
                data = copy.deepcopy(self.server.data)
            if path.endswith("events"):
                payload = ("retry: 2000\ndata: " + json.dumps(data) + "\n\n").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            return self.reply(data)
        if path.startswith("/api/"):
            return self.reply({"detail": "Unavailable in sample preview"}, 404)
        target = (DIST / path.lstrip("/")).resolve()
        if not target.is_relative_to(DIST.resolve()):
            return self.reply({"detail": "Invalid path"}, 400)
        if not target.is_file():
            target = DIST / "index.html"
        payload = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        self.mutate()

    def do_PUT(self):
        self.mutate()

    def mutate(self):
        port = self.server.server_port
        if self.headers.get("Origin") not in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}:
            return self.reply({"detail": "Origin rejected"}, 403)
        if self.headers.get("X-CSRF-Token") != "sample-preview-only":
            return self.reply({"detail": "Preview token required"}, 403)
        path = urlparse(self.path).path
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 <= size <= 65536:
                return self.reply({"detail": "Preview request too large"}, 413)
            body = json.loads(self.rfile.read(size)) if size else {}
        except (ValueError, TypeError):
            return self.reply({"detail": "Invalid request"}, 400)
        with self.server.lock:
            data = self.server.data
            if path in {"/api/scan", "/api/logout"}:
                return self.reply({"ok": True})
            if path.startswith("/api/queue/"):
                data["settings"]["paused"] = path.endswith("pause")
                return self.reply(data["settings"])
            if path == "/api/settings":
                data["settings"].update({k: v for k, v in body.items() if k in SETTINGS})
                return self.reply(data["settings"])
            if path.startswith("/api/jobs/"):
                parts = path.split("/")
                job = next((j for j in data["jobs"] if j["id"] == parts[3]), None)
                if job and len(parts) == 5:
                    if parts[4] == "metadata":
                        for key in ("title", "description", "privacy", "tags", "made_for_kids"):
                            if key in body:
                                job[key] = body[key]
                    elif parts[4] in {"pause", "retry", "resume", "exclude"}:
                        job["state"] = {"pause": "PAUSED", "exclude": "SKIPPED"}.get(parts[4], "QUEUED")
                        job["error"] = ""
                    return self.reply({"ok": True})
        return self.reply({"detail": "Preview only: folder access, Google connection and file transfers are disabled. Use the full app for real archiving."}, 409)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not (DIST / "index.html").is_file():
        raise SystemExit("Dashboard build missing. Run npm ci and npm run build in frontend, or use the preview ZIP.")
    server = PreviewServer(args.port)
    address = f"http://127.0.0.1:{server.server_port}"
    print(f"TubeVault UI preview: {address}\nSample data only. No Google calls or video uploads.\nPress Ctrl+C to stop.", flush=True)
    if not args.no_browser:
        webbrowser.open(address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
