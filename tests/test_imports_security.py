from pathlib import Path
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from tubevault.imports import Imports, safe_name
from tubevault.config import Config
from tubevault.api import create_app


@pytest.mark.parametrize("name", ["../escape.mp4", "C:\\escape.mp4", "CON.mp4", "bad:stream", "x/../../y", "trailing.", "NUL", "a\x00b"])
def test_reject_unsafe_names(name):
    with pytest.raises(ValueError):
        safe_name(name)


def test_import_retry_exact_bytes_and_duplicate_finish(db, video, tmp_path):
    service = Imports(db, tmp_path / "inbox")
    original = video.read_bytes()
    transfer = service.create("বাংলা.mp4", "Trip", len(original))
    assert service.append(transfer, 0, original[:100]) == 100
    with pytest.raises(ValueError):
        service.append(transfer, 0, original[:100])
    # Simulate crash after filesystem write but before database commit.
    with (service.temp / transfer).open("ab") as f:
        f.write(b"uncommitted")
    service.append(transfer, 100, original[100:])
    target = service.finish(transfer)
    assert Path(target).read_bytes() == original
    assert not (service.temp / transfer).exists()
    assert service.finish(transfer) == target
    assert video.read_bytes() == original


def test_auth_csrf_host_and_limits(db, tmp_path):
    config = Config(data_dir=tmp_path, password="a secure test password", allowed_hosts="testserver", origins="http://testserver")
    app = create_app(config, db, (Mock(), Mock(), Mock(), Mock()), background=False)
    with TestClient(app) as client:
        assert client.get('/api/snapshot').status_code == 401
        assert client.post('/api/login', json={"password": config.password}).status_code == 403
        response = client.post('/api/login', json={"password": config.password}, headers={"Origin": "http://testserver"})
        assert response.status_code == 200
        csrf = response.json()["csrf"]
        assert client.get('/api/snapshot').status_code == 200
        assert client.post('/api/queue/resume').status_code == 403
        headers = {"Origin": "http://testserver", "X-CSRF-Token": csrf}
        assert client.post('/api/queue/resume', headers=headers).status_code == 200
        assert client.post('/api/imports', headers=headers, json={"filename": "../x.mp4", "collection": "trip", "size": 42}).status_code == 400
        assert client.get('/api/snapshot', headers={"Host": "evil.example"}).status_code == 400
        assert client.put('/api/imports/test?offset=0', headers=headers | {"Content-Length": "999999999"}).status_code == 413
        assert client.post('/api/logout', headers=headers).status_code == 200
        assert client.get('/api/snapshot').status_code == 401


def test_login_rate_limit(db, tmp_path):
    config = Config(data_dir=tmp_path, password="a secure test password", allowed_hosts="testserver", origins="http://testserver")
    with TestClient(create_app(config, db, (Mock(), Mock(), Mock(), Mock()), background=False)) as client:
        for _ in range(10):
            assert client.post('/api/login', json={"password": "wrong"}, headers={"Origin": "http://testserver"}).status_code == 401
        assert client.post('/api/login', json={"password": "wrong"}, headers={"Origin": "http://testserver"}).status_code == 429



def test_completed_phone_import_queues_immediately_without_other_roots(db, video, tmp_path):
    from sqlalchemy import select
    from tubevault.db import Job, Instance, Watch
    from tubevault.scanner import Scanner

    imports = Imports(db, tmp_path / "phone-inbox")
    transfer = imports.create("phone.mov", "iPhone memories", video.stat().st_size)
    imports.append(transfer, 0, video.read_bytes())
    target = imports.finish(transfer)
    with db.session() as session:
        session.add(Watch(path=str(video.parents[1]), stability=0))
    scanner = Scanner(db)
    scanner.scan_import(target, imports.root)
    scanner.scan_import(target, imports.root)
    with db.session() as session:
        jobs = list(session.scalars(select(Job)))
        assert len(jobs) == 1
        assert session.get(Instance, jobs[0].instance_id).path == target
        assert session.scalar(select(Watch).where(Watch.path == str(imports.root))).stability == 30
    assert Path(target).read_bytes() == video.read_bytes()
