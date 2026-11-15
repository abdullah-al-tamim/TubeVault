import os
import time
from unittest.mock import Mock

from fastapi.testclient import TestClient
from sqlalchemy import select

from tubevault.api import create_app
from tubevault.config import Config
from tubevault.db import Event, Job
from tubevault.scanner import Scanner
from tubevault.history import control_history


def test_history_visibility_preserves_completion_and_deduplication(db, video):
    original = video.read_bytes()
    os.utime(video, (time.time() - 120, time.time() - 120))
    Scanner(db).add_files([str(video)])
    with db.session() as s:
        job = s.scalar(select(Job))
        job.state = "COMPLETED"
        job.video_id = "abcdefghijk"
        job_id = job.id
    assert control_history(db, [job_id, job_id, "missing"], "remove")["results"] == [
        {"id": job_id, "ok": True, "error": None},
        {"id": "missing", "ok": False, "error": "Video not found"},
    ]
    control_history(db, [job_id], "remove")
    Scanner(db).add_files([str(video)])
    with db.session() as s:
        job = s.get(Job, job_id)
        assert job.history_hidden and job.state == "COMPLETED" and job.video_id == "abcdefghijk"
        assert len(list(s.scalars(select(Job)))) == 1
        assert len(list(s.scalars(select(Event).where(Event.kind == "history_visibility")))) == 1
    assert control_history(db, [job_id], "restore")["results"][0]["ok"]
    with db.session() as s:
        assert not s.get(Job, job_id).history_hidden
        s.get(Job, job_id).claimed = True
    assert not control_history(db, [job_id], "remove")["results"][0]["ok"]
    with db.session() as s:
        s.get(Job, job_id).claimed = False
        s.get(Job, job_id).state = "QUEUED"
    assert not control_history(db, [job_id], "remove")["results"][0]["ok"]
    assert video.read_bytes() == original


def test_history_removal_is_authenticated_durable_and_preserves_evidence(db, video, tmp_path):
    original = video.read_bytes()
    os.utime(video, (time.time() - 120, time.time() - 120))
    Scanner(db).add_files([str(video)])
    with db.session() as s:
        job = s.scalar(select(Job))
        job.state = "COMPLETED"
        job.video_id = "abcdefghijk"
        job_id = job.id
    config = Config(data_dir=tmp_path, password="a secure test password", allowed_hosts="testserver", origins="http://testserver")
    with TestClient(create_app(config, db, (Mock(), Mock(), Mock(), Mock()), background=False)) as client:
        body = {"ids": [job_id, job_id, "missing"], "action": "remove"}
        assert client.post("/api/history/bulk", json=body).status_code == 401
        origin = {"Origin": "http://testserver"}
        csrf = client.post("/api/login", json={"password": config.password}, headers=origin).json()["csrf"]
        assert client.post("/api/history/bulk", json=body, headers=origin).status_code == 403
        headers = origin | {"X-CSRF-Token": csrf}
        results = client.post("/api/history/bulk", json=body, headers=headers).json()["results"]
        assert len(results) == 2 and results[0]["ok"] and not results[1]["ok"]
        snapshot = client.get("/api/snapshot").json()
        assert snapshot["jobs"][0]["history_hidden"] is True
        assert snapshot["stats"]["archived"] == 1
        with db.session() as s:
            job = s.get(Job, job_id)
            assert job.state == "COMPLETED" and job.video_id == "abcdefghijk"
            assert len(list(s.scalars(select(Event).where(Event.kind == "history_visibility")))) == 1
        Scanner(db).add_files([str(video)])
        with db.session() as s:
            assert len(list(s.scalars(select(Job)))) == 1
        assert client.post("/api/history/bulk", json={"ids": [job_id], "action": "restore"}, headers=headers).json()["results"][0]["ok"]
        with db.session() as s:
            job = s.get(Job, job_id)
            assert not job.history_hidden
            job.state = "QUEUED"
        assert not client.post("/api/history/bulk", json={"ids": [job_id], "action": "remove"}, headers=headers).json()["results"][0]["ok"]
        assert client.post("/api/history/bulk", json={"ids": [], "action": "remove"}, headers=headers).status_code == 422
    assert video.read_bytes() == original
