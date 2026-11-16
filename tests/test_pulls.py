from unittest.mock import Mock
from pathlib import Path
import json

import pytest
from fastapi.testclient import TestClient

from tubevault.api import create_app
from tubevault.config import Config
from tubevault.pulls import Pulls
from tubevault import pull_transport as transport

VIDEO = "abcdefghijk"
LINK = f"https://youtu.be/{VIDEO}?t=3"


def test_select_and_validate():
    assert transport.video_id(LINK) == VIDEO
    assert transport.video_id(f"https://www.youtube.com/shorts/{VIDEO}") == VIDEO
    for link in ["https://example.org/" + VIDEO, "https://youtube.com/playlist?list=x"]:
        with pytest.raises(ValueError):
            transport.video_id(link)
    assert "[height<=1080]" in transport.selection("mp4", 1080)[1]
    with pytest.raises(ValueError):
        transport.selection("mp3", 1080)


def test_pull_from_api_to_file(db, tmp_path, monkeypatch):
    def runner(args, cwd, **kwargs):
        assert args[-1] == f"https://www.youtube.com/watch?v={VIDEO}"
        assert "--ignore-config" in args and "--no-playlist" in args
        path = cwd / f"{VIDEO}.mkv"
        path.write_bytes(b"mock media")
        return Mock(returncode=0, stdout=json.dumps(dict(filepath=str(path), height=2160, title="Trip")))
    monkeypatch.setattr(transport.shutil, "which", lambda exe, path: exe)
    monkeypatch.setattr(transport.subprocess, "run", runner)
    config = Config(data_dir=tmp_path, password="a secure test password", allowed_hosts="testserver", origins="http://testserver")
    with TestClient(create_app(config, db, (Mock(),) * 4, background=False)) as client:
        assert client.get("/api/pulls").status_code == 401
        headers = {"Origin": "http://testserver"}
        headers["X-CSRF-Token"] = client.post("/api/login", json={"password": config.password}, headers=headers).json()["csrf"]
        assert client.post("/api/pulls", json={"url": LINK}).status_code == 403
        created = client.post("/api/pulls", json={"url": LINK}, headers=headers)
        assert created.status_code == 202
        record, = client.get("/api/pulls").json()
        assert record["state"] == "Ready" and record["actual_height"] == 2160
        assert client.get(f"/api/pulls/{record['id']}/file").content == b"mock media"


def test_pull_restart_and_tool_failure(tmp_path, monkeypatch):
    service = Pulls(tmp_path)
    _, lock = service.prepare(LINK, "source", None)
    assert service.recent()[0]["state"] == "Pulling"
    lock.release()
    assert Pulls(tmp_path).recent()[0]["state"] == "Interrupted"
    monkeypatch.setattr(transport.shutil, "which", lambda exe, path: None)
    assert service.finish(*service.prepare(LINK, "mp3", None))["state"] == "Failed"

@pytest.mark.skipif(transport.os.name != "nt", reason="Windows WinGet layout")
def test_winget_links_after_desktop_start(tmp_path, monkeypatch):
    links = tmp_path / "Microsoft" / "WinGet" / "Links"
    links.mkdir(parents=True)
    tool = links / "tubevault-test-tool.exe"
    tool.touch()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("PATH", str(tmp_path))
    assert str(links) in transport.tool_path().split(transport.os.pathsep)
    assert Path(transport.shutil.which(tool.stem, path=transport.tool_path())) == tool

def test_flat_output_and_legacy_history(tmp_path, monkeypatch):
    legacy = tmp_path / ("1" * 32)
    legacy.mkdir()
    source = legacy / f"{VIDEO}.mkv"
    source.write_bytes(b"existing")
    receipt = dict(id=legacy.name, video_id=VIDEO, title="Trip: ঢাকা", state="Ready", path=str(source))
    (legacy / "status.json").write_text(json.dumps(receipt))
    service = Pulls(tmp_path)
    output = tmp_path / "Trip_ ঢাকা_tubevault.mkv"
    assert output.read_bytes() == b"existing"
    assert not legacy.exists()
    assert service.recent()[0]["path"] == str(output)

    def download(folder, source_id, kind, height):
        staged = folder / f"{source_id}.mkv"
        staged.write_bytes(b"second")
        return dict(path=str(staged), title=receipt["title"])
    monkeypatch.setattr("tubevault.pulls.download", download)
    record = service.finish(*service.prepare(LINK, "source", None))
    assert Path(record["path"]) == tmp_path / "Trip_ ঢাকা (2)_tubevault.mkv"
    assert Path(record["path"]).read_bytes() == b"second"
    assert output.read_bytes() == b"existing"
    assert len(Pulls(tmp_path).recent()) == 2
