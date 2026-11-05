import random
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from sqlalchemy import select, update
from .db import Job, Instance, Identity, Mapping, UploadSession, Video, Account, Attempt, Notification, Setting, transition
from .scanner import digest
from .youtube import APIError

ELIGIBLE = ["QUEUED", "UPLOADING", "PROCESSING", "PLAYLIST_PENDING", "FAILED_RETRYABLE"]


def allowed(settings, now=None):
    if settings["paused"] or settings["cooldown"] > time.time():
        return False
    if settings["mode"] != "scheduled":
        return True
    hour = (now or datetime.now(ZoneInfo(settings["timezone"]))).hour
    start, end = settings["start_hour"], settings["end_hour"]
    return start <= hour < end if start < end else hour >= start or hour < end


def metered():
    """Windows network cost via WinRT; unknown cost fails closed when requested."""
    try:
        import subprocess
        command = "[Windows.Networking.Connectivity.NetworkInformation,Windows,ContentType=WindowsRuntime]::GetInternetConnectionProfile().GetConnectionCost().NetworkCostType.ToString()"
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                                capture_output=True, text=True, timeout=10, creationflags=0x08000000)
        return result.stdout.strip() != "Unrestricted"
    except (OSError, subprocess.TimeoutExpired):
        return True


class Worker:
    def __init__(self, db, youtube, secrets):
        self.db, self.youtube, self.secrets = db, youtube, secrets
        self.stop = threading.Event()
        self.network_blocked = threading.Event()
        self.playlist_lock = threading.Lock()

    def recover(self):
        with self.db.session() as s:
            for job in s.scalars(select(Job).where(Job.claimed == True)):
                job.claimed = False
                if job.state == "UPLOADING":
                    transition(s, job, "UPLOADING", "Recovered; server session will be probed")

    def claim(self):
        with self.db.session() as s:
            job_id = s.scalar(select(Job.id).where(Job.state.in_(ELIGIBLE), Job.claimed == False,
                                                   Job.next_attempt <= time.time()).order_by(Job.created).limit(1))
            if not job_id:
                return None
            result = s.execute(update(Job).where(Job.id == job_id, Job.claimed == False).values(claimed=True))
            return job_id if result.rowcount == 1 else None

    def step(self):
        settings = self.db.settings()
        if not allowed(settings) or self.stop.is_set():
            return
        job_id = self.claim()
        if not job_id:
            return
        try:
            self.run(job_id)
        except APIError as e:
            with self.db.session() as s:
                job = s.get(Job, job_id)
                job.retries += 1
                job.next_attempt = time.time() + min(3600, 2 ** min(job.retries, 11)) + random.uniform(0, 5)
                state = "FAILED_RETRYABLE" if e.retryable or e.quota else "FAILED_PERMANENT"
                if not job.video_id and e.reason in {"http_404", "http_410"}:
                    state = "UPLOAD_UNCERTAIN"
                transition(s, job, state, e.reason)
                s.add(Attempt(job_id=job.id, reason=e.reason))
            if e.quota:
                self.db.configure({"cooldown": time.time() + 86400})
        except Exception as e:
            # Class names aid diagnosis without leaking HTTP URLs/tokens or OAuth responses.
            with self.db.session() as s:
                job = s.get(Job, job_id)
                transition(s, job, "FAILED_RETRYABLE", type(e).__name__)
                job.next_attempt = time.time() + 120
        finally:
            with self.db.session() as s:
                s.get(Job, job_id).claimed = False

    def run(self, job_id):
        with self.db.session() as s:
            job = s.get(Job, job_id)
            instance, identity = s.get(Instance, job.instance_id), s.get(Identity, job.identity_id)
            account = s.scalar(select(Account))
            if not account:
                raise APIError("Connect_YouTube_first", retryable=True)
            if job.account_id and job.account_id != account.id:
                raise APIError("Channel_mismatch")
            job.account_id = account.id
            session = s.get(UploadSession, job_id)
        if not job.video_id:
            path = Path(instance.path)
            st = path.stat()
            if (st.st_size, st.st_mtime_ns) != (instance.size, instance.mtime_ns) or digest(path) != identity.sha256:
                raise APIError("Source_changed")
            if not session:
                # Commit intent before external side effect. A crash before URI persistence is ambiguous.
                if job.state == "UPLOADING":
                    with self.db.session() as s:
                        transition(s, s.get(Job, job_id), "UPLOAD_UNCERTAIN", "Session initiation outcome unknown")
                    return
                with self.db.session() as s:
                    transition(s, s.get(Job, job_id), "UPLOADING")
                try:
                    uri = self.youtube.start(job, identity.size)
                    secret_key = "upload-" + job_id
                    self.secrets.set(secret_key, uri)
                    with self.db.session() as s:
                        s.add(UploadSession(job_id=job_id, secret_key=secret_key))
                    session = UploadSession(job_id=job_id, secret_key=secret_key, offset=0)
                except Exception as e:
                    with self.db.session() as s:
                        if isinstance(e, APIError) and (e.quota or not e.retryable):
                            transition(s, s.get(Job, job_id), "FAILED_RETRYABLE" if e.quota else "FAILED_PERMANENT", e.reason)
                        else:
                            transition(s, s.get(Job, job_id), "UPLOAD_UNCERTAIN", "Session creation could not be confirmed")
                    if isinstance(e, APIError) and e.quota:
                        self.db.configure({"cooldown": time.time() + 86400})
                    return
            uri = self.secrets.get(session.secret_key)
            if not uri:
                with self.db.session() as s:
                    transition(s, s.get(Job, job_id), "UPLOAD_UNCERTAIN", "Session credential missing")
                return
            with self.db.session() as s:
                transition(s, s.get(Job, job_id), "UPLOADING", "Probing saved session")
            response = self.youtube.probe(uri, identity.size)
            offset, video_id = self.ack(response, identity.size)
            with path.open("rb") as source:
                while not video_id and offset < identity.size:
                    if self.stop.is_set() or self.network_blocked.is_set() or not allowed(self.db.settings()):
                        return
                    with self.db.session() as s:
                        if s.get(Job, job_id).state in {"PAUSED", "SKIPPED"}:
                            return
                    if (path.stat().st_size, path.stat().st_mtime_ns) != (instance.size, instance.mtime_ns):
                        raise APIError("Source_changed")
                    source.seek(offset)
                    block = source.read(8 * 1024 * 1024)
                    before = time.monotonic()
                    response = self.youtube.chunk(uri, identity.size, offset, block)
                    next_offset, video_id = self.ack(response, identity.size)
                    if not video_id and next_offset <= offset:
                        raise APIError("No_upload_progress", retryable=True)
                    speed = len(block) / max(.01, time.monotonic() - before)
                    offset = next_offset
                    with self.db.session() as s:
                        current = s.get(Job, job_id)
                        current.progress, current.speed = offset, speed
                        s.get(UploadSession, job_id).offset = offset
                    bandwidth = self.db.settings()["bandwidth_kbps"]
                    if bandwidth:
                        self.stop.wait(max(0, len(block) / (bandwidth * 1024) - (time.monotonic() - before)))
            if not video_id:
                raise APIError("Awaiting_final_response", retryable=True)
            with self.db.session() as s:
                current = s.get(Job, job_id)
                current.video_id, current.progress = video_id, identity.size
                s.merge(Video(id=video_id, identity_id=identity.id, account_id=account.id, privacy=job.privacy))
                transition(s, current, "PROCESSING")
            job.video_id = video_id
        video = self.youtube.video(job.video_id)
        if video["snippet"]["channelId"] != account.id:
            raise APIError("Video_channel_mismatch")
        processing = video.get("processingDetails", {}).get("processingStatus", "processing")
        if video.get("status", {}).get("uploadStatus") in {"rejected", "failed", "deleted"} or processing in {"failed", "terminated"}:
            raise APIError("YouTube_processing_failed")
        with self.db.session() as s:
            record = s.get(Video, job.video_id)
            if record:
                record.processing = processing
            current = s.get(Job, job_id)
            if processing != "succeeded":
                transition(s, current, "PROCESSING")
                current.next_attempt = time.time() + 60
                return
            transition(s, current, "PLAYLIST_PENDING")
        with self.playlist_lock:
            with self.db.session() as s:
                mapping = s.get(Mapping, job.mapping_id)
            intent_key = "playlist-intent-" + mapping.id
            def before_create():
                with self.db.session() as s:
                    if s.get(Setting, intent_key):
                        raise APIError("Playlist_creation_uncertain_select_existing_ID")
                    s.add(Setting(key=intent_key, value={"attempted": time.time()}))
            playlist_id = self.youtube.ensure_playlist(mapping, before_create=before_create)
            with self.db.session() as s:
                current_mapping = s.get(Mapping, job.mapping_id)
                current_mapping.playlist_id, current_mapping.account_id = playlist_id, account.id
                intent = s.get(Setting, intent_key)
                if intent:
                    s.delete(intent)
            self.youtube.insert(playlist_id, job.video_id)
        with self.db.session() as s:
            transition(s, s.get(Job, job_id), "COMPLETED")
            if self.db.settings()["notifications"]:
                s.add(Notification(message=f"Archived {job.title}"))

    @staticmethod
    def ack(response, size):
        if response.status_code in (200, 201):
            video_id = response.json().get("id")
            if not video_id:
                raise APIError("Missing_video_ID", retryable=True)
            return size, video_id
        value = response.headers.get("Range", "")
        offset = int(value.split("-")[-1]) + 1 if value else 0
        if not 0 <= offset <= size:
            raise APIError("Invalid_server_offset")
        return offset, None
