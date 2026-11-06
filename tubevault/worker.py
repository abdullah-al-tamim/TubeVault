import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from sqlalchemy import select, update
from .db import Job, Instance, Identity, Mapping, UploadSession, Video, Account, Attempt, Event, Notification, Setting, transition
from .scanner import digest
from .youtube import APIError

ELIGIBLE = ["QUEUED", "UPLOADING", "PROCESSING", "PLAYLIST_PENDING", "FAILED_RETRYABLE", "UPLOAD_UNCERTAIN"]
RETRY_SECONDS = 300


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
        from .duplicates import DuplicateGuard
        self.duplicates = DuplicateGuard(db, youtube)

    def recover(self):
        with self.db.session() as s:
            for job in s.scalars(select(Job).where(Job.claimed == True)):
                job.claimed = False
                if job.state == "UPLOADING" and not s.get(UploadSession, job.id):
                    self.wait_for_retry(s, job, "Upload setup was interrupted before transfer", "UPLOAD_UNCERTAIN")
                elif job.control_requested and job.state not in {"UPLOAD_UNCERTAIN", "COMPLETED"}:
                    transition(s, job, job.control_requested, "Recovered pending user control")
                elif job.state == "UPLOADING":
                    transition(s, job, "UPLOADING", "Recovered; server session will be probed")

    @staticmethod
    def wait_for_retry(s, job, reason, state="FAILED_RETRYABLE"):
        job.next_attempt = time.time() + RETRY_SECONDS
        job.retries += 1
        job.speed = 0
        transition(s, job, state, reason)

    def claim(self):
        with self.db.session() as s:
            job_id = s.scalar(select(Job.id).where(Job.state.in_(ELIGIBLE), Job.claimed == False, Job.control_requested == "",
                                                   Job.next_attempt <= time.time()).order_by(Job.created).limit(1))
            if not job_id:
                return None
            result = s.execute(update(Job).where(Job.id == job_id, Job.claimed == False, Job.control_requested == "", Job.state.in_(ELIGIBLE)).values(claimed=True))
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
                if job.state == "UPLOAD_UNCERTAIN":
                    self.wait_for_retry(s, job, "YouTube verification paused: " + e.reason, job.state)
                elif not job.video_id and s.get(UploadSession, job.id) and e.status in {404, 410}:
                    self.wait_for_retry(s, job, "Upload session expired; checking YouTube for completion", "UPLOAD_UNCERTAIN")
                elif e.retryable or e.quota:
                    self.wait_for_retry(s, job, e.reason)
                else:
                    transition(s, job, "FAILED_PERMANENT", e.reason)
                s.add(Attempt(job_id=job.id, reason=e.reason))
            if e.quota or e.reason in {"Google sign-in expired; reconnect in Settings", "Google sign-in required; connect in Settings"}:
                self.db.configure({"cooldown": time.time() + RETRY_SECONDS, "cooldown_reason": e.reason})
        except Exception as e:
            with self.db.session() as s:
                job = s.get(Job, job_id)
                state = "UPLOAD_UNCERTAIN" if job.state == "UPLOAD_UNCERTAIN" else "FAILED_RETRYABLE"
                self.wait_for_retry(s, job, "Temporary error: " + type(e).__name__, state)
        finally:
            with self.db.session() as s:
                current = s.get(Job, job_id)
                current.claimed = False
                if current.control_requested and current.state not in {"UPLOAD_UNCERTAIN", "COMPLETED"}:
                    transition(s, current, current.control_requested, "Stopped after current operation; progress retained")
                    current.speed = 0

    def interrupted(self, job_id):
        with self.db.session() as s:
            return bool(s.get(Job, job_id).control_requested) or self.stop.is_set() or self.network_blocked.is_set() or not allowed(self.db.settings())

    def run(self, job_id):
        if self.interrupted(job_id):
            return
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
        if job.state == "UPLOAD_UNCERTAIN":
            # Older builds committed this audit event before probing or sending any bytes.
            # Require a recorded setup and no transfer checkpoint before discarding a lost session.
            with self.db.session() as s:
                events = set(s.scalars(select(Event.message).where(
                    Event.job_id == job.id, Event.kind == "transition")))
                never_sent = not job.video_id and not job.progress and (
                    session is None or (
                        session.offset == 0 and not self.secrets.get(session.secret_key)
                        and any(message.endswith("UPLOADING: ") for message in events)
                        and not any(message.endswith("Probing saved session") for message in events)
                    ))
                if never_sent:
                    if session:
                        s.delete(s.get(UploadSession, job_id))
                    transition(s, s.get(Job, job_id), "QUEUED", "Retrying upload setup; no video bytes were sent")
            if not never_sent:
                self.verify_completion(job, account, identity)
                return
            session = None
            job.state = "QUEUED"
        if not job.video_id:
            path = Path(instance.path)
            st = path.stat()
            if (st.st_size, st.st_mtime_ns) != (instance.size, instance.mtime_ns) or digest(path) != identity.sha256:
                raise APIError("Source_changed")
            if self.interrupted(job_id):
                return
            if not session:
                # Commit intent before external side effect. A crash before URI persistence is ambiguous.
                if job.state == "UPLOADING":
                    with self.db.session() as s:
                        self.wait_for_retry(s, s.get(Job, job_id), "Upload setup was interrupted before transfer", "UPLOAD_UNCERTAIN")
                    return
                with self.duplicates.lock:
                    inventory = self.duplicates.inventory()
                    if self.duplicates.match(job_id, inventory):
                        return
                    if self.interrupted(job_id):
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
                except APIError as error:
                    if error.retryable or error.quota:
                        self.db.configure({"cooldown": time.time() + RETRY_SECONDS, "cooldown_reason": error.reason})
                    raise
                except Exception as e:
                    # Session setup sends metadata only. No bytes were transferred.
                    raise APIError("Could not save upload session: " + type(e).__name__, retryable=True) from None
            if self.interrupted(job_id):
                return
            uri = self.secrets.get(session.secret_key)
            if not uri:
                with self.db.session() as s:
                    self.wait_for_retry(s, s.get(Job, job_id), "Saved session unavailable; checking YouTube for completion", "UPLOAD_UNCERTAIN")
                return
            with self.db.session() as s:
                transition(s, s.get(Job, job_id), "UPLOADING", "Probing saved session")
            response = self.youtube.probe(uri, identity.size)
            offset, video_id = self.ack(response, identity.size)
            if not video_id:
                with self.duplicates.lock:
                    if self.duplicates.match(job_id, self.duplicates.inventory(), include_session=True):
                        return
            with path.open("rb") as source:
                while not video_id and offset < identity.size:
                    if self.interrupted(job_id):
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
        if self.interrupted(job_id):
            return
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
        if self.interrupted(job_id):
            return
        with self.playlist_lock:
            if self.interrupted(job_id):
                return
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
            if self.interrupted(job_id):
                return
            self.youtube.insert(playlist_id, job.video_id)
        with self.db.session() as s:
            transition(s, s.get(Job, job_id), "COMPLETED")
            if self.db.settings()["notifications"]:
                s.add(Notification(message=f"Archived {job.title}"))

    def verify_completion(self, job, account, identity):
        inventory = self.duplicates.inventory()
        matches = [video for video in inventory["videos"] if video.get("job_id") == job.id]
        if len(matches) == 1:
            video = self.youtube.video(matches[0]["id"])
            snippet = video["snippet"]
            if snippet["channelId"] != account.id or f"TubeVault job {job.id}" not in snippet.get("description", "").splitlines():
                matches = []
        with self.db.session() as s:
            current = s.get(Job, job.id)
            if len(matches) != 1:
                reason = ("Several YouTube videos match this upload" if matches else
                          "Saved session unavailable and YouTube has not confirmed completion")
                self.wait_for_retry(s, current, reason, "UPLOAD_UNCERTAIN")
                return
            video = matches[0]
            current.video_id, current.progress = video["id"], identity.size
            s.merge(Video(id=video["id"], identity_id=identity.id, account_id=account.id, privacy=job.privacy))
            current.next_attempt = 0
            transition(s, current, "PROCESSING", "Existing upload found on YouTube")

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
