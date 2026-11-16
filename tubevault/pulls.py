"""Durable local pull receipts shared by the API and editor command."""
import argparse
import json
import time
from pathlib import Path
from uuid import uuid4

from filelock import FileLock, Timeout
from .pull_transport import FORMATS, HEIGHTS, download, selection, video_id


def save(folder, record):
    pending = folder / "status.tmp"
    pending.write_text(json.dumps(record), encoding="utf-8")
    pending.replace(folder / "status.json")


class Pulls:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def prepare(self, url, kind, height):
        source = video_id(url)
        selection(kind, height)
        key = uuid4().hex
        folder = self.root / key
        folder.mkdir(parents=True)
        lock = FileLock(folder / "active.lock", thread_local=False)
        lock.acquire()
        record = dict(id=key, video_id=source, format=kind, height=height,
                      created=time.time(), state="Pulling", path=None, error="")
        try:
            save(folder, record)
        except Exception:
            lock.release()
            raise
        return record, lock

    def finish(self, record, lock):
        folder = self.root / record["id"]
        try:
            try:
                media = download(folder, record["video_id"], record["format"], record["height"])
                record = dict(record, state="Ready", **media)
            except RuntimeError as exc:
                record = dict(record, state="Failed", error=str(exc))
            except Exception:
                record = dict(record, state="Failed", error="Pull interrupted. Check local storage and tools, then retry.")
            save(folder, record)
            return record
        finally:
            lock.release()

    def get(self, folder):
        receipt = folder / "status.json"
        record = json.loads(receipt.read_text(encoding="utf-8"))
        if record["state"] == "Pulling":
            try:
                with FileLock(folder / "active.lock", timeout=0):
                    record = json.loads(receipt.read_text(encoding="utf-8"))
                    if record["state"] == "Pulling":
                        record.update(state="Interrupted", error="TubeVault stopped before confirming the file. Start a new pull.")
                        save(folder, record)
            except Timeout:
                pass
        return record

    def recent(self):
        folders = sorted(self.root.glob("*/status.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [self.get(p.parent) for p in folders[:100]]


def main():
    parser = argparse.ArgumentParser(description="Fetch one YouTube video for a local edit.")
    parser.add_argument("url")
    parser.add_argument("--format", choices=FORMATS, default="source")
    parser.add_argument("--height", type=int, choices=HEIGHTS)
    parser.add_argument("--output", type=Path, default=Path.home() / "TubeVault" / "data" / "pulls")
    args = parser.parse_args()
    service = Pulls(args.output)
    try:
        result = service.finish(*service.prepare(args.url, args.format, args.height))
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result))
    return 0 if result["state"] == "Ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
