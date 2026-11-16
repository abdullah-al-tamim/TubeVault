"""Durable local pull receipts shared by the API and editor command."""
import argparse
import json
import os
import re
import time
from pathlib import Path
from itertools import count
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
        self.jobs = self.root / ".tubevault"
        self.jobs.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def publish(self, folder, record):
        source = Path(record["staged"])
        if source.parent != folder or source.stem != record["video_id"] or not re.fullmatch(r"\.[a-zA-Z0-9]{1,8}", source.suffix):
            raise ValueError("Unexpected staged media path")
        title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", record.get("title") or record["video_id"])
        with FileLock(self.jobs / "publish.lock"):
            for number in count(1):
                extra = "" if number == 1 else f" ({number})"
                ending = extra + "_tubevault" + source.suffix
                limit = 255 - len(ending)
                stem = title.encode("utf-16-le")[:2 * limit].decode("utf-16-le", "ignore")
                name = stem + ending
                if Path(name).is_reserved():
                    name = "_" + title.encode("utf-16-le")[:2 * (limit-1)].decode("utf-16-le", "ignore") + ending
                target = self.root / name
                if not source.exists():
                    target = Path(record["path"])
                    if target.parent != self.root or not target.is_file():
                        raise FileNotFoundError("Published media is missing")
                    break
                if os.path.lexists(target):
                    if not target.is_symlink() and source.samefile(target):
                        source.unlink()
                        break
                    continue
                record.update(path=str(target), state="Publishing")
                save(folder, record)
                try:
                    if os.name == "nt":
                        source.rename(target)
                    else:
                        os.link(source, target)
                        source.unlink()
                except FileExistsError:
                    continue
                break
            record.update(state="Ready", path=str(target))
            record.pop("staged")
            save(folder, record)
            return record

    def migrate(self):
        with FileLock(self.jobs / "migration.lock"):
            for receipt in self.root.glob("*/status.json"):
                old = receipt.parent
                if not re.fullmatch(r"[0-9a-f]{32}", old.name) or old.resolve() != old:
                    continue
                try:
                    record = json.loads(receipt.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if record.get("id") != old.name or record.get("state") == "Pulling":
                    continue
                if record["state"] == "Ready" and Path(record["path"]).parent == old:
                    source = Path(record["path"])
                    if source.is_file() and source.resolve() == source:
                        record.update(staged=str(source), state="Publishing")
                        save(old, record)
                if record["state"] == "Publishing":
                    try:
                        self.publish(old, record)
                    except PermissionError:
                        source = Path(record["staged"])
                        if source.is_file():
                            record.update(path=str(source), state="Ready")
                            record.pop("staged")
                            save(old, record)
                        continue
                dest = self.jobs / old.name
                if not dest.exists() and all(p.name in {"active.lock","status.json"} for p in old.iterdir()):
                    try:
                        old.rename(dest)
                    except PermissionError:
                        continue

    def prepare(self, url, kind, height):
        source = video_id(url)
        selection(kind, height)
        key = uuid4().hex
        folder = self.jobs / key
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
        folder = self.jobs / record["id"]
        try:
            try:
                media = download(folder, record["video_id"], record["format"], record["height"])
                record = dict(record, state="Publishing", **media)
                record["staged"] = record["path"]
                save(folder, record)
                return self.publish(folder, record)
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
        if record["state"] in {"Pulling", "Publishing"}:
            try:
                with FileLock(folder / "active.lock", timeout=0):
                    record = json.loads(receipt.read_text(encoding="utf-8"))
                    if record["state"] == "Publishing":
                        return self.publish(folder, record)
                    if record["state"] == "Pulling":
                        record.update(state="Interrupted", error="TubeVault stopped before confirming the file. Start a new pull.")
                        save(folder, record)
            except Timeout:
                pass
        return record

    def recent(self):
        folders = sorted([*self.jobs.glob("*/status.json"), *self.root.glob("*/status.json")], key=lambda p: p.stat().st_mtime, reverse=True)
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
