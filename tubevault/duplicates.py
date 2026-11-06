"""Read-only channel inventory and conservative title matching."""
import threading
import time
import unicodedata
from sqlalchemy import select
from .db import Account, Job, Setting, UploadSession, transition
from .youtube import APIError

def title_key(title):
    return " ".join(unicodedata.normalize("NFC", title).casefold().split())

class DuplicateGuard:
    def __init__(self, db, youtube):
        self.db, self.youtube = db, youtube
        self.lock = threading.RLock()

    def inventory(self):
        inventory = self.youtube.uploaded_videos()
        with self.db.session() as s:
            account = s.scalar(select(Account))
            if not account or account.id != inventory["channel_id"]:
                raise APIError("Channel_mismatch")
            value = inventory | {"checked_at": time.time()}
            s.merge(Setting(key="youtube-title-inventory", value=value))
        return inventory

    def match(self, job_id, inventory, include_session=False):
        with self.db.session() as s:
            job = s.get(Job, job_id)
            if job.video_id or (not include_session and s.get(UploadSession, job_id)):
                return None  # Resume the existing session; never initiate a second one.
            key = title_key(job.title)
            matches = [v["id"] for v in inventory["videos"] if title_key(v["title"]) == key]
            # Reserve titles already started locally, including ambiguous attempts not yet listed by YouTube.
            for other in s.scalars(select(Job).where(Job.id != job.id)):
                if title_key(other.title) == key and (other.video_id or other.state in {"UPLOADING", "UPLOAD_UNCERTAIN"} or s.get(UploadSession, other.id)):
                    matches.append(other.video_id or ("local-job:" + other.id))
            if matches:
                transition(s, job, "DUPLICATE_TITLE", "Matching title already exists: " + ", ".join(dict.fromkeys(matches)))
                return matches
        return None

    def review_queue(self):
        with self.lock:
            inventory = self.inventory()
            held = []
            with self.db.session() as s:
                ids = list(s.scalars(select(Job.id).where(Job.claimed == False, Job.state.in_(["QUEUED", "UPLOADING", "FAILED_RETRYABLE", "DUPLICATE_TITLE"]))))
            for job_id in ids:
                if self.match(job_id, inventory, include_session=True):
                    held.append(job_id)
            counts = {}
            for video in inventory["videos"]:
                counts.setdefault(title_key(video["title"]), []).append(video)
            return {"checked": len(inventory["videos"]), "held": len(held), "duplicate_titles": [v for v in counts.values() if len(v) > 1]}
