"""Read-only channel inventory and conservative title matching."""
import threading
import time
import unicodedata
from sqlalchemy import select
from .db import Account, Event, Job, Setting, UploadSession, transition
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

    def match(self, job_id, inventory, include_session=False, reviewing=False):
        with self.db.session() as s:
            job = s.get(Job, job_id)
            if reviewing and (job.claimed or job.control_requested or job.state not in {"QUEUED", "UPLOADING", "FAILED_RETRYABLE", "DUPLICATE_TITLE"}):
                return None
            if job.video_id or (not include_session and s.get(UploadSession, job_id)):
                return None  # Resume the existing session; never initiate a second one.
            key = title_key(job.title)
            matches = [v["id"] for v in inventory["videos"] if title_key(v["title"]) == key]
            channel_matches = set(matches)
            # Reserve titles already started locally, including ambiguous attempts not yet listed by YouTube.
            for other in s.scalars(select(Job).where(Job.id != job.id)):
                if title_key(other.title) == key and (other.video_id or other.state in {"UPLOADING", "UPLOAD_UNCERTAIN"} or s.get(UploadSession, other.id)):
                    matches.append(other.video_id or ("local-job:" + other.id))
            if (len(channel_matches) == 1 and set(matches) == channel_matches
                and not s.get(UploadSession, job_id) and job.state != "UPLOADING"
                and job.account_id in (None, inventory["channel_id"])):
                job.video_id = channel_matches.pop()
                job.account_id = inventory["channel_id"]
                job.next_attempt = 0
                s.add(Event(kind="title_link", job_id=job.id, message="Reused existing channel video by title"))
                transition(s, job, "PROCESSING", "Existing YouTube video found; checking processing before playlist insertion")
                return "linked"
            if matches:
                transition(s, job, "DUPLICATE_TITLE", "Matching title already exists: " + ", ".join(dict.fromkeys(matches)))
                return "held"
        return None

    def review_queue(self):
        with self.lock:
            inventory = self.inventory()
            held = linked = 0
            with self.db.session() as s:
                ids = list(s.scalars(select(Job.id).where(Job.claimed == False, Job.state.in_(["QUEUED", "UPLOADING", "FAILED_RETRYABLE", "DUPLICATE_TITLE"]))))
            for job_id in ids:
                outcome = self.match(job_id, inventory, include_session=True, reviewing=True)
                held += outcome == "held"
                linked += outcome == "linked"
            counts = {}
            for video in inventory["videos"]:
                counts.setdefault(title_key(video["title"]), []).append(video)
            return {"checked": len(inventory["videos"]), "held": held, "linked": linked, "duplicate_titles": [v for v in counts.values() if len(v) > 1]}
