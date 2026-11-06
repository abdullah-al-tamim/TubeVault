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
    yt.uploaded_videos.return_value = {"channel_id":"channel", "videos":[]}
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


def test_pause_during_final_chunk_retains_video_and_blocks_playlist(db, rig):
    from tubevault.queue_controls import control_jobs
    worker, yt, job_id = rig
    def chunk(*args):
        assert control_jobs(db, [job_id], "pause")["results"][0]["ok"]
        return httpx.Response(200, json={"id":"abcdefghijk"})
    yt.chunk.side_effect = chunk
    worker.step()
    with db.session() as s:
        job = s.get(Job, job_id)
        assert job.state == "PAUSED"
        assert job.video_id == "abcdefghijk"
        assert not job.claimed
    yt.insert.assert_not_called()
    control_jobs(db, [job_id], "resume")
    worker.step()
    assert yt.start.call_count == 1
    yt.insert.assert_called_once()


def test_cancel_during_upload_error_is_not_retried(db, rig):
    from tubevault.queue_controls import control_jobs
    worker, yt, job_id = rig
    def chunk(*args):
        control_jobs(db, [job_id], "cancel")
        raise APIError("network", retryable=True)
    yt.chunk.side_effect = chunk
    worker.step()
    with db.session() as s:
        assert s.get(Job, job_id).state == "CANCELLED"
        assert s.get(UploadSession, job_id)
    assert worker.claim() is None


def test_bulk_remove_persists_across_scan_and_can_restore(db, rig):
    from tubevault.queue_controls import control_jobs
    worker, yt, job_id = rig
    result = control_jobs(db, [job_id, "missing"], "remove")
    assert [r["ok"] for r in result["results"]] == [True, False]
    Scanner(db).scan()
    assert worker.claim() is None
    control_jobs(db, [job_id], "resume")
    assert worker.claim() == job_id


def test_remote_title_duplicate_never_starts_upload(db, rig):
    worker, yt, job_id = rig
    with db.session() as s:
        title=s.get(Job,job_id).title
    yt.uploaded_videos.return_value={"channel_id":"channel","videos":[{"id":"remotevideo","title":title.upper()}]}
    worker.step()
    yt.start.assert_not_called()
    with db.session() as s:
        assert s.get(Job,job_id).state=="DUPLICATE_TITLE"
        assert s.get(Job,job_id).video_id is None


def test_title_check_failure_blocks_new_session(db, rig):
    worker, yt, job_id = rig
    yt.uploaded_videos.side_effect=APIError("Network interruption",retryable=True)
    worker.step()
    yt.start.assert_not_called()
    with db.session() as s:
        assert s.get(Job,job_id).state=="FAILED_RETRYABLE"


def test_saved_session_resumes_without_new_session(db, rig):
    worker, yt, job_id = rig
    yt.chunk.side_effect=APIError("network",retryable=True)
    worker.step()
    with db.session() as s:
        s.get(Job,job_id).next_attempt=0
    yt.chunk.side_effect=None
    worker.step()
    assert yt.start.call_count==1


def test_paused_active_video_releases_slot_for_next_job(db, rig):
    from tubevault.queue_controls import control_jobs
    worker,yt,job_id=rig
    with db.session() as s:
        original=s.get(Job,job_id)
        other=Job(identity_id=original.identity_id,instance_id=original.instance_id,mapping_id=original.mapping_id,title="Different title")
        s.add(other);s.flush();other_id=other.id
    def chunk(*args):
        control_jobs(db,[job_id],"pause")
        return httpx.Response(308,headers={"Range":"bytes=0-255"})
    yt.chunk.side_effect=chunk
    worker.step()
    assert db.settings()['paused'] is False
    assert worker.claim()==other_id


def test_local_title_reservation_prevents_second_session(db, rig):
    worker,yt,job_id=rig
    with db.session() as s:
        original=s.get(Job,job_id)
        original.state="UPLOAD_UNCERTAIN"
        other=Job(identity_id=original.identity_id,instance_id=original.instance_id,mapping_id=original.mapping_id,title=original.title)
        s.add(other);s.flush();other_id=other.id
    worker.step()
    yt.start.assert_not_called()
    with db.session() as s:
        assert s.get(Job,other_id).state=="DUPLICATE_TITLE"


def test_partial_session_with_remote_matching_title_is_held(db, rig):
    worker,yt,job_id=rig
    yt.chunk.side_effect=APIError("network",retryable=True)
    worker.step()
    with db.session() as s:
        job=s.get(Job,job_id);job.next_attempt=0;title=job.title
    yt.uploaded_videos.return_value={"channel_id":"channel","videos":[{"id":"otherremote","title":title}]}
    yt.chunk.reset_mock()
    worker.step()
    yt.chunk.assert_not_called()
    assert yt.start.call_count==1
    with db.session() as s:
        assert s.get(Job,job_id).state=="DUPLICATE_TITLE"
        assert s.get(UploadSession,job_id) is not None
