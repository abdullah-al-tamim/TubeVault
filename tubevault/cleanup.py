"""Explicit local cleanup for sources with a verified TubeVault archive."""
import stat
from pathlib import Path

from sqlalchemy import select

from .db import Account, Event, Identity, Instance, Job
from .scanner import digest
from .youtube import APIError


class Cleanup:
    def __init__(self, db, youtube, scanner):
        self.db = db
        self.youtube = youtube
        self.scanner = scanner

    def candidates(self):
        with self.db.session() as session:
            rows = list(session.execute(
                select(Job, Instance, Identity)
                .join(Instance, Job.instance_id == Instance.id)
                .join(Identity, Job.identity_id == Identity.id)
                .join(Account, Job.account_id == Account.id)
                .where(Job.state == "COMPLETED", Job.video_id.is_not(None),
                       Instance.identity_id == Job.identity_id)
                .order_by(Job.created)
            ))
        candidates = {}
        for job, instance, identity in rows:
            try:
                self.inspect_source(instance)
            except (OSError, ValueError):
                continue
            candidates.setdefault(instance.id, (job, instance, identity))
        return candidates

    @staticmethod
    def inspect_source(instance):
        path = Path(instance.path)
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            or path.resolve(strict=True) != path
            or (info.st_size, info.st_mtime_ns) != (instance.size, instance.mtime_ns)):
            raise ValueError("Original changed or is not a regular local file")
        return path, info

    def preview(self):
        return [{"id": instance.id, "path": instance.path, "size": identity.size,
                 "video_id": job.video_id} for job, instance, identity in self.candidates().values()]

    def delete(self, ids):
        results = []
        with self.scanner.lock:
            with self.db.session() as session:
                if not self.db.settings()["paused"] or session.scalar(select(Job.id).where(Job.claimed).limit(1)):
                    raise ValueError("Pause the upload queue and wait for active uploads to stop")
            candidates = self.candidates()
            for instance_id in dict.fromkeys(ids):
                entry = candidates.get(instance_id)
                if entry is None:
                    results.append({"id": instance_id, "ok": False, "reason": "Original is no longer eligible"})
                    continue
                job, instance, identity = entry
                try:
                    remote = self.youtube.video(job.video_id)
                    if (remote["snippet"]["channelId"] != job.account_id
                        or f"TubeVault job {job.id}" not in remote["snippet"].get("description", "").splitlines()
                        or remote.get("status", {}).get("uploadStatus") != "processed"):
                        raise ValueError("YouTube could not verify the processed archive")
                    path, before = self.inspect_source(instance)
                    if digest(path) != identity.sha256:
                        raise ValueError("Original contents changed")
                    _, after = self.inspect_source(instance)
                    if (before.st_ino, before.st_dev, before.st_ctime_ns) != (after.st_ino, after.st_dev, after.st_ctime_ns):
                        raise ValueError("Original was replaced during verification")
                    with self.db.session() as session:
                        if not self.db.settings()["paused"] or session.scalar(select(Job.id).where(
                            Job.instance_id == instance.id, Job.state != "COMPLETED").limit(1)):
                            raise ValueError("Queue resumed or this original has another upload job")
                    path.unlink()
                    with self.db.session() as session:
                        session.add(Event(kind="source_cleanup", job_id=job.id, message="User deleted verified local original"))
                    results.append({"id": instance_id, "ok": True})
                except (APIError, KeyError):
                    results.append({"id": instance_id, "ok": False, "reason": "YouTube verification unavailable"})
                except OSError:
                    results.append({"id": instance_id, "ok": False, "reason": "File unavailable or locked"})
                except ValueError as error:
                    results.append({"id": instance_id, "ok": False, "reason": str(error)})
        return results
