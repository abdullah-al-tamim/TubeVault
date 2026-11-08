"""Receiver tests use a fake LAN address and an in-process HTTP client."""
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tubevault.db import Job, Instance
from tubevault.imports import Imports
from tubevault.scanner import Scanner
from tubevault.phone_receiver import PhoneReceiver


@pytest.fixture
def receiver(db, tmp_path):
    value = PhoneReceiver(Imports(db, tmp_path / "inbox"), Scanner(db))
    value.url = "http://192.168.1.20:8766"
    value.collection = "iPhone memories"
    value.invitation = "a" * 43
    value.deadline = time.time() + 43200
    value.pair_deadline = time.time() + 600
    value.server = SimpleNamespace(should_exit=False)
    return value


def pair(client, receiver):
    response = client.post("/pair", json={"invitation": receiver.invitation}, headers={"Origin": receiver.url})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["token"], "Origin": receiver.url}


def test_pairing_is_single_use_and_upload_only(receiver):
    invitation = receiver.invitation
    with TestClient(receiver.create_app("192.168.1.20"), base_url=receiver.url) as client:
        assert client.get("/status").status_code == 401
        assert client.post("/pair", json={"invitation": invitation}, headers={"Origin": "https://evil.example"}).status_code == 401
        headers = pair(client, receiver)
        assert client.post("/pair", json={"invitation": invitation}, headers={"Origin": receiver.url}).status_code == 401
        for path in ("/api/snapshot", "/api/login", "/api/queue/resume", "/client_secret.json"):
            assert client.get(path, headers=headers).status_code == 404
        assert client.get("/status", headers=headers).status_code == 200
        assert client.get("/status", headers=headers | {"Host": "evil.example"}).status_code == 400
        receiver.stop()
        assert client.get("/status", headers=headers).status_code == 401


def test_expired_invitation_cannot_pair(receiver):
    receiver.pair_deadline = time.time() - 1
    with TestClient(receiver.create_app("192.168.1.20"), base_url=receiver.url) as client:
        assert client.post("/pair", json={"invitation": receiver.invitation},
                           headers={"Origin": receiver.url}).status_code == 401


def test_connection_test_is_authenticated_bounded_and_creates_no_files(receiver):
    with TestClient(receiver.create_app("192.168.1.20"), base_url=receiver.url) as client:
        assert client.post("/connection-test", content=b"x").status_code == 401
        headers = pair(client, receiver)
        assert client.post("/connection-test", content=b"x", headers=headers).status_code == 400
        assert client.post("/connection-test", content=b"x" * (1024 * 1024 + 1), headers=headers).status_code == 413
        result = client.post("/connection-test", content=b"x" * (1024 * 1024), headers=headers)
        assert result.status_code == 200
        assert result.json()["bytes"] == 1024 * 1024
        assert result.json()["receive_seconds"] >= 0
        assert not receiver.transfers
        assert not list(receiver.imports.temp.iterdir())


def test_phone_chunk_resume_finish_queues_exact_original(receiver, db, video):
    original = video.read_bytes()
    with TestClient(receiver.create_app("192.168.1.20"), base_url=receiver.url) as client:
        headers = pair(client, receiver)
        response = client.post("/files", json={"filename": "phone.mov", "size": len(original)}, headers=headers)
        transfer_id = response.json()["id"]
        path = "/files/" + transfer_id
        assert client.put(path + "?offset=0", content=original[:100], headers=headers).json()["offset"] == 100
        assert client.put(path + "?offset=0", content=original[:100], headers=headers).status_code == 409
        assert client.get(path, headers=headers).json()["offset"] == 100
        assert client.post(path + "/finish", headers=headers).status_code == 409
        assert client.put(path + "?offset=100", content=original[100:], headers=headers).status_code == 200
        assert client.post(path + "/finish", headers=headers).json()["saved"]
        assert client.post(path + "/finish", headers=headers).json()["saved"]
        assert receiver.completed == 1
        with db.session() as session:
            jobs = list(session.scalars(select(Job)))
            assert len(jobs) == 1
            from pathlib import Path
            assert Path(session.get(Instance, jobs[0].instance_id).path).read_bytes() == original
        assert db.settings()["paused"]
        assert client.get("/files/guessed", headers=headers).status_code == 404
        assert client.post("/files", json={"filename": "../bad.mov", "size": 10}, headers=headers).status_code == 400
        with patch("tubevault.phone_receiver.shutil.disk_usage", return_value=SimpleNamespace(free=0)):
            assert client.post("/files", json={"filename": "full.mov", "size": 10}, headers=headers).status_code == 409
        assert client.put(path + "?offset=0", content=original, headers=headers | {"Origin": "https://evil.example"}).status_code == 403
        receiver.deadline = time.time() - 1
        assert client.put(path + "?offset=0", content=original, headers=headers).status_code == 401


def test_new_receiver_cannot_access_another_sessions_transfers(receiver):
    with TestClient(receiver.create_app("192.168.1.20"), base_url=receiver.url) as client:
        headers = pair(client, receiver)
        first = client.post("/files", json={"filename": "phone.mov", "size": 100}, headers=headers).json()["id"]
        receiver.transfers = set()
        assert client.get("/files/" + first, headers=headers).status_code == 404



def test_real_receiver_start_pair_stop_uses_separate_port(db, tmp_path):
    import httpx
    receiver = PhoneReceiver(Imports(db, tmp_path / "network-inbox"), Scanner(db))
    with patch("tubevault.phone_receiver.private_ipv4", return_value=True):
        result = receiver.start("127.0.0.1", "Phone")
    try:
        assert result["qr"].startswith("data:image/png;base64,")
        invitation = result["url"].split("#pair=")[1]
        with httpx.Client(base_url=receiver.url, trust_env=False) as client:
            assert client.get("/").status_code == 200
            assert client.get("/phone.js").status_code == 200
            paired = client.post("/pair",json={"invitation":invitation},headers={"Origin":receiver.url})
            assert paired.status_code == 200
            assert client.get("/status",headers={"Authorization":"Bearer "+paired.json()["token"]}).status_code == 200
    finally:
        receiver.stop()
