import os
import re
import threading
from pathlib import Path
from sqlalchemy import select
from .db import Transfer, Watch
from .scanner import EXTENSIONS, digest, video_signature


def safe_name(name):
    if (not name or len(name) > 150 or name in {".", ".."} or name.endswith((".", " "))
        or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
        or name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(10)], *[f"LPT{i}" for i in range(10)]}):
        raise ValueError("Unsafe filename or collection name")
    return name


class Imports:
    def __init__(self, db, root):
        self.db, self.root, self.lock = db, root.resolve(), threading.Lock()
        self.temp = self.root / ".transfers"
        self.temp.mkdir(parents=True, exist_ok=True)
        with db.session() as s:
            if not s.scalar(select(Watch).where(Watch.path == str(self.root))):
                s.add(Watch(path=str(self.root), excludes=[".transfers", ".transfers/*"], stability=30))

    def create(self, filename, collection, size):
        safe_name(filename)
        safe_name(collection)
        if collection.startswith(".") or Path(filename).suffix.lower() not in EXTENSIONS:
            raise ValueError("Unsupported file or collection")
        if not 0 < size <= 256_000_000_000:
            raise ValueError("Invalid transfer size")
        with self.db.session() as s:
            transfer = Transfer(filename=filename, collection=collection, size=size)
            s.add(transfer)
            s.flush()
            return transfer.id

    def append(self, transfer_id, offset, data):
        with self.lock, self.db.session() as s:
            row = s.get(Transfer, transfer_id)
            if not row:
                raise ValueError("Unknown transfer")
            if row.state != "RECEIVING" or row.offset != offset:
                raise ValueError("Offset conflict; query transfer before retrying")
            if not 0 < len(data) <= 8 * 1024 * 1024 or offset + len(data) > row.size:
                raise ValueError("Invalid chunk size")
            path = self.temp / row.id
            with path.open("r+b" if path.exists() else "xb") as f:
                # SQLite is authoritative after a crash between fsync and commit.
                f.truncate(offset)
                f.seek(offset)
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            row.offset += len(data)
            return row.offset

    def finish(self, transfer_id):
        with self.lock:
            with self.db.session() as s:
                row = s.get(Transfer, transfer_id)
                if not row or row.offset != row.size:
                    raise ValueError("Transfer incomplete")
                if row.state == "INGESTED":
                    return row.destination
            path = self.temp / row.id
            folder = self.root / row.collection
            folder.mkdir(exist_ok=True)
            if not folder.resolve().is_relative_to(self.root) or folder.is_symlink():
                raise ValueError("Invalid destination")
            target = folder / (row.id + "-" + row.filename)
            # Hard-link is atomic, exclusive, same-volume and preserves original bytes.
            if not target.exists():
                if not video_signature(path):
                    raise ValueError("Unrecognized video container")
                sha = digest(path)
                os.link(path, target)
            else:
                sha = digest(target)
                if path.exists() and digest(path) != sha:
                    raise ValueError("Destination conflict")
            with self.db.session() as s:
                current = s.get(Transfer, transfer_id)
                current.sha256, current.destination, current.state = sha, str(target), "INGESTED"
            # Temporary hardlink retained deliberately; cleanup is explicit, never source deletion.
            return str(target)
