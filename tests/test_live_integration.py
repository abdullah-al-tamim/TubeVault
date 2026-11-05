"""Explicit opt-in only. Never deletes the remote test video/playlist."""
import os
import time
from pathlib import Path
import pytest
from sqlalchemy import select
from tubevault.auth import Auth, Secrets
from tubevault.config import config
from tubevault.db import Database, Base, Account, Watch, Job, Mapping
from tubevault.scanner import Scanner
from tubevault.worker import Worker
from tubevault.youtube import YouTube


@pytest.mark.integration
def test_authorized_real_upload():
    if os.environ.get("TUBEVAULT_ALLOW_LIVE_UPLOAD") != "I_AUTHORIZE_ONE_PRIVATE_TEST_UPLOAD":
        pytest.skip("Requires explicit authorization and user-supplied tiny video")
    source = Path(os.environ["TUBEVAULT_LIVE_VIDEO"]).resolve(strict=True)
    assert source.is_file() and source.stat().st_size < 10 * 1024 * 1024
    # Dedicated history stays durable if this test is interrupted; no automatic cleanup.
    target = config.data_dir / "live-integration"
    target.mkdir(parents=True, exist_ok=True)
    db = Database(target / "history.db")
    Base.metadata.create_all(db.engine)
    secrets = Secrets()
    yt = YouTube(Auth(db, secrets, config))
    account = yt.request("GET", "channels", params={"part": "snippet", "mine": "true"}).json()["items"][0]
    with db.session() as s:
        s.merge(Account(id=account["id"], name=account["snippet"]["title"]))
        if not s.scalar(select(Watch)):
            s.add(Watch(path=str(source.parent), depth=0, stability=0, excludes=[p.name for p in source.parent.iterdir() if p.name != source.name]))
    Scanner(db).scan()
    with db.session() as s:
        jobs = list(s.scalars(select(Job)))
        assert len(jobs) == 1, "Use a folder containing only the chosen tiny video"
        job_id = jobs[0].id
    db.configure({"paused": False, "pause_metered": False})
    worker = Worker(db, yt, secrets)
    worker.recover()
    deadline = time.time() + 600
    while time.time() < deadline:
        worker.step()
        with db.session() as s:
            job = s.get(Job, job_id)
            if job.state == "COMPLETED":
                playlist = s.get(Mapping, job.mapping_id).playlist_id
                assert any(item["contentDetails"]["videoId"] == job.video_id for item in yt.list_all("playlistItems", {"part": "contentDetails", "playlistId": playlist, "maxResults": 50}))
                return
            assert job.state not in {"UPLOAD_UNCERTAIN", "FAILED_PERMANENT"}, job.error
        time.sleep(5)
    pytest.fail("Processing did not finish within ten minutes; inspect durable integration history")
