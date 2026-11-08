import fnmatch
import hashlib
import os
import threading
import time
from pathlib import Path
from sqlalchemy import select
from .db import Watch, Mapping, Identity, Instance, Job, Event

EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".mpeg", ".mpg", ".wmv", ".flv", ".3gp", ".mts", ".m2ts"}


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(4 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(path, size):
    with open(path, "rb") as f:
        head = f.read(65536)
        f.seek(max(0, size - 65536))
        return hashlib.sha256(str(size).encode() + head + f.read(65536)).hexdigest()


def video_signature(path):
    with open(path, "rb") as f:
        b = f.read(1024)
    return (b"ftyp" in b[:64] or b.startswith((b"\x1aE\xdf\xa3", b"RIFF", b"FLV", b"\x00\x00\x01", b"\x30\x26\xb2\x75"))
            or len(b) > 192 and (b[0] == 0x47 or b[4] == 0x47))


class Scanner:
    def __init__(self, db):
        self.db, self.lock = db, threading.Lock()

    def scan_import(self, path, root):
        """Queue an atomically completed phone import without scanning other roots."""
        path, root = Path(path).resolve(strict=True), Path(root).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Imported video is outside the inbox")
        with self.lock:
            with self.db.session() as s:
                watch = s.scalar(select(Watch).where(Watch.path == str(root)))
            if watch is None or not watch.enabled:
                return
            # Imports.finish has already verified and atomically published the whole file.
            watch.stability = 0
            self._file(watch, root, path, self.db.settings())

    def add_files(self, paths):
        from .queue_controls import control_jobs
        results = []
        with self.lock:
            for raw in dict.fromkeys(paths):
                try:
                    path = Path(raw).resolve(strict=True)
                    if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
                        raise ValueError("Choose a supported video file")
                    if time.time() - path.stat().st_mtime < 60:
                        raise ValueError("File is recent; wait 60 seconds after copying finishes")
                    with self.db.session() as s:
                        watches = list(s.scalars(select(Watch)))
                        matches = [w for w in watches if path.is_relative_to(Path(w.path))]
                        watch = max(matches, key=lambda w: len(w.path)) if matches else None
                        if watch is None:
                            watch = Watch(path=str(path.parent), enabled=False, automatic=False, stability=60)
                            s.add(watch)
                            s.flush()
                    # Explicit selection does not enable a parent-folder scan.
                    watch.stability = 0
                    watch.unsorted = True
                    watch.excludes = []
                    self._file(watch, Path(watch.path), path, self.db.settings())
                    with self.db.session() as s:
                        instance = s.scalar(select(Instance).where(Instance.path == str(path)))
                        job = s.scalar(select(Job).where(Job.identity_id == instance.identity_id).order_by(Job.created)) if instance and instance.identity_id else None
                        if not job:
                            raise ValueError(instance.reason if instance else "File could not be queued")
                        job_id, state = job.id, job.state
                    if state in {"PAUSED", "SKIPPED", "CANCELLED", "REMOVED"}:
                        result = control_jobs(self.db, [job_id], "resume")["results"][0]
                        if not result["ok"]:
                            raise ValueError(result["error"])
                    results.append({"path": str(path), "ok": True, "message": "Already archived" if state == "COMPLETED" else "Added or already queued"})
                except (OSError, ValueError) as error:
                    results.append({"path": raw, "ok": False, "message": str(error) if isinstance(error, ValueError) else "File unavailable"})
        return {"results": results}

    def scan(self, watch_id=None, automatic=False):
        with self.lock:
            with self.db.session() as s:
                watches = list(s.scalars(select(Watch).where(Watch.enabled == True)))
            for w in watches:
                if watch_id and w.id != watch_id or automatic and not w.automatic:
                    continue
                try:
                    self._watch(w)
                except OSError:
                    with self.db.session() as s:
                        s.add(Event(kind="scan_error", message=f"Watch folder unavailable: {w.path}"))

    def _watch(self, w):
        root = Path(w.path).resolve(strict=True)
        paths = []
        for folder, dirs, files in os.walk(root, followlinks=False):
            base = Path(folder)
            depth = len(base.relative_to(root).parts)
            dirs[:] = [d for d in dirs if depth < w.depth and not (base / d).is_symlink()
                       and not any(fnmatch.fnmatch((base / d).relative_to(root).as_posix(), p) for p in w.excludes)]
            for name in files:
                p = base / name
                if p.is_symlink() or not p.resolve().is_relative_to(root):
                    continue
                paths.append(p)
        settings = self.db.settings()
        paths.sort(key=(lambda p: (p.stat().st_mtime_ns, str(p))) if settings["sort"] == "date" else lambda p: str(p).casefold())
        for p in paths:
            try:
                self._file(w, root, p, settings)
            except OSError:
                continue

    def _file(self, w, root, p, settings):
        relative = p.relative_to(root)
        if len(relative.parts) == 1 and not w.unsorted:
            return
        folder = root / relative.parts[0] if len(relative.parts) > 1 else root
        st = folder.stat()
        folder_key = f"{st.st_dev}:{st.st_ino}"
        stat = p.stat()
        now = time.time()
        with self.db.session() as s:
            mapping = s.scalar(select(Mapping).where(Mapping.watch_id == w.id, Mapping.folder_key == folder_key))
            if not mapping:
                title = folder.name if folder != root else root.name + " — Unsorted"
                if s.scalar(select(Mapping).where(Mapping.title == title, Mapping.watch_id != w.id)):
                    title = root.name + " — " + title
                mapping = Mapping(watch_id=w.id, folder_key=folder_key, path=str(folder),
                                  title=title, privacy=w.privacy)
                s.add(mapping)
                s.flush()
            mapping.path = str(folder)
            instance = s.scalar(select(Instance).where(Instance.path == str(p)))
            if not instance:
                instance = Instance(path=str(p), mapping_id=mapping.id, size=stat.st_size, mtime_ns=stat.st_mtime_ns, stable_since=now)
                s.add(instance)
            elif (instance.size, instance.mtime_ns) != (stat.st_size, stat.st_mtime_ns):
                instance.size, instance.mtime_ns = stat.st_size, stat.st_mtime_ns
                instance.stable_since, instance.identity_id, instance.reason = now, None, "STABILIZING"
            if instance.identity_id:
                return
            reason = ""
            if p.suffix.lower() not in EXTENSIONS:
                reason = "Unsupported extension"
            elif any(fnmatch.fnmatch(relative.as_posix(), pattern) or fnmatch.fnmatch(p.name, pattern) for pattern in w.excludes):
                reason = "Excluded by pattern"
            elif not 0 < stat.st_size <= w.max_bytes:
                reason = "Outside configured size limit"
            if reason:
                instance.reason = reason
                return
            if now - instance.stable_since < w.stability:
                return
            instance_id, mapping_id, privacy = instance.id, mapping.id, mapping.privacy
            s.flush()
            instance_id = instance.id
        if not video_signature(p):
            with self.db.session() as s:
                s.get(Instance, instance_id).reason = "Unrecognized video container"
            return
        sha, fast = digest(p), fingerprint(p, stat.st_size)
        after = p.stat()
        if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
            return
        with self.db.session() as s:
            instance = s.get(Instance, instance_id)
            identity = s.scalar(select(Identity).where(Identity.sha256 == sha))
            if not identity:
                identity = Identity(sha256=sha, fingerprint=fast, size=stat.st_size)
                s.add(identity)
                s.flush()
            instance.identity_id = identity.id
            duplicate = s.scalar(select(Job).where(Job.identity_id == identity.id))
            if duplicate:
                old_instance = s.get(Instance, duplicate.instance_id)
                if not Path(old_instance.path).exists() and not duplicate.claimed:
                    duplicate.instance_id = instance.id
                instance.reason = "Duplicate content: " + duplicate.id
                return
            instance.reason = "QUEUED"
            title = settings["title_template"].replace("{filename}", p.name).replace("{folder}", folder.name)
            description = settings["description_template"].replace("{filename}", p.name).replace("{folder}", folder.name)
            job = Job(identity_id=identity.id, instance_id=instance.id, mapping_id=mapping_id,
                      title=title[:100], description=description[:4900], privacy=privacy)
            s.add(job)
            s.flush()
            s.add(Event(kind="discovered", job_id=job.id, message=f"Queued {p.name}"))
