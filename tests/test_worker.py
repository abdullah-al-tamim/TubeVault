from datetime import datetime
from unittest.mock import Mock
import httpx
import pytest
from sqlalchemy import select
from tubevault.db import Watch, Job, Account, UploadSession, DEFAULTS, Mapping
from tubevault.scanner import Scanner
from tubevault.worker import Worker, allowed
from tubevault.youtube import APIError, YouTube


class MemorySecrets:
    def __init__(self):
        self.values = {}
    def get(self, key):
        return self.values.get(key)
    def set(self, key, value):
        self.values[key] = value


@pytest.fixture
def rig(db, video):
    with db.session() as s:
        s.add(Watch(path=str(video.parents[1]), stability=0))
        s.add(Account(id="channel", name="Test"))
    Scanner(db).scan()
    db.configure({"paused": False, "pause_metered": False})
    yt = Mock()
    yt.start.return_value = "https://www.googleapis.com/upload/test"
    yt.probe.return_value = httpx.Response(308)
    yt.chunk.return_value = httpx.Response(200, json={"id": "abcdefghijk"})
    yt.video.return_value = {"snippet": {"channelId": "channel"}, "processingDetails": {"processingStatus": "succeeded"}, "status": {"privacyStatus": "private"}}
    yt.ensure_playlist.return_value = "playlist"
    worker = Worker(db, yt, MemorySecrets())
    with db.session() as s:
        job_id = s.scalar(select(Job.id))
    return worker, yt, job_id


def test_upload_original_and_playlist_failure_never_reuploads(db, video, rig):
    worker, yt, job_id = rig
    yt.insert.side_effect = APIError("rateLimitExceeded", retryable=True)
    worker.step()
    with db.session() as s:
        job = s.get(Job, job_id)
        assert job.video_id == "abcdefghijk"
        assert job.state == "FAILED_RETRYABLE"
        job.next_attempt = 0
    assert yt.chunk.call_args.args[-1] == video.read_bytes()
    yt.insert.side_effect = None
    worker.step()
    assert yt.start.call_count == 1
    assert yt.chunk.call_count == 1
    with db.session() as s:
        assert s.get(Job, job_id).state == "COMPLETED"


def test_network_interruption_resumes_server_offset(db, rig):
    worker, yt, job_id = rig
    yt.chunk.side_effect = APIError("Network interruption", retryable=True)
    worker.step()
    with db.session() as s:
        s.get(Job, job_id).next_attempt = 0
    yt.probe.return_value = httpx.Response(308, headers={"Range": "bytes=0-255"})
    yt.chunk.side_effect = None
    worker.step()
    assert yt.start.call_count == 1
    assert yt.chunk.call_args.args[2] == 256


def test_expired_session_blocks_duplicate(db, rig):
    worker, yt, job_id = rig
    yt.probe.side_effect = APIError("http_404")
    worker.step()
    worker.step()
    assert yt.start.call_count == 1
    with db.session() as s:
        assert s.get(Job, job_id).state == "UPLOAD_UNCERTAIN"


def test_crash_after_intent_has_no_blind_restart(db, rig):
    worker, yt, job_id = rig
    with db.session() as s:
        job = s.get(Job, job_id)
        job.state, job.claimed = "UPLOADING", True
    worker.recover()
    worker.step()
    yt.start.assert_not_called()
    with db.session() as s:
        assert s.get(Job, job_id).state == "UPLOAD_UNCERTAIN"


def test_claim_exclusion(db, rig):
    worker, _, job_id = rig
    assert worker.claim() == job_id
    assert worker.claim() is None


def test_concurrent_claim_has_single_owner(db, rig):
    from concurrent.futures import ThreadPoolExecutor
    worker, _, job_id = rig
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda _: worker.claim(), range(4)))
    assert claims.count(job_id) == 1


def test_quota_at_session_creation_can_retry_without_uncertainty(db, rig):
    worker, yt, job_id = rig
    yt.start.side_effect = APIError("quotaExceeded", quota=True)
    worker.step()
    with db.session() as s:
        assert s.get(Job, job_id).state == "FAILED_RETRYABLE"
    assert db.settings()["cooldown"] > 0


def test_quota_cooldown(db, rig):
    worker, yt, _ = rig
    yt.video.side_effect = APIError("quotaExceeded", quota=True)
    worker.step()
    assert db.settings()["cooldown"] > 0
    assert not allowed(db.settings())


def test_processing_is_not_completion(db, rig):
    worker, yt, job_id = rig
    yt.video.return_value["processingDetails"]["processingStatus"] = "processing"
    worker.step()
    yt.insert.assert_not_called()
    with db.session() as s:
        assert s.get(Job, job_id).state == "PROCESSING"


def test_source_changes_fail_before_upload(db, video, rig):
    worker, yt, job_id = rig
    video.write_bytes(b"changed")
    worker.step()
    yt.start.assert_not_called()
    with db.session() as s:
        assert s.get(Job, job_id).error == "Source_changed"


@pytest.mark.parametrize("hour,expected", [(22,True),(2,True),(12,False),(6,False)])
def test_midnight_schedule(hour, expected):
    settings = DEFAULTS | {"paused": False, "mode": "scheduled", "start_hour": 22, "end_hour": 6}
    assert allowed(settings, datetime(2026, 1, 1, hour)) == expected


def test_transport_explicit_privacy_and_errors():
    auth = Mock()
    auth.token.return_value = "not-a-real-token"
    yt = YouTube(auth)
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, headers={"Location": "https://www.googleapis.com/upload/test"})
    yt.client = httpx.Client(transport=httpx.MockTransport(respond))
    job = Mock(title="Original", description="", id="job", tags=[], privacy="private", made_for_kids=False)
    yt.start(job, 100)
    import json
    assert json.loads(requests[0].content)["status"]["privacyStatus"] == "private"
    yt.client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403, json={"error": {"errors": [{"reason": "quotaExceeded"}]}})))
    with pytest.raises(APIError) as exc:
        yt.playlists()
    assert exc.value.quota


def test_playlist_marker_reuse_and_membership():
    yt = YouTube(Mock())
    yt.playlists = Mock(return_value=[{"id": "existing", "snippet": {"title": "Renamed on YouTube", "description": "TubeVault collection internal"}}])
    mapping = Mapping(id="internal", title="Local title", privacy="private")
    assert yt.ensure_playlist(mapping) == "existing"
    yt.list_all = Mock(return_value=[{"contentDetails": {"videoId": "video"}}])
    yt.request = Mock()
    yt.insert("existing", "video")
    yt.request.assert_not_called()


def test_ambiguous_playlist_creation_requires_reconciliation(db, rig):
    worker, yt, job_id = rig
    attempts = []
    def ambiguous(mapping, before_create):
        before_create()
        attempts.append(mapping.id)
        raise APIError("Network interruption", retryable=True)
    yt.ensure_playlist.side_effect = ambiguous
    worker.step()
    with db.session() as s:
        s.get(Job, job_id).next_attempt = 0
    worker.step()
    assert len(attempts) == 1
    with db.session() as s:
        job = s.get(Job, job_id)
        assert job.video_id == 'abcdefghijk'
        assert job.error == 'Playlist_creation_uncertain_select_existing_ID'
    assert yt.start.call_count == 1
