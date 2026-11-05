import pytest
from tubevault.db import Database, Base


@pytest.fixture
def db(tmp_path):
    value = Database(tmp_path / "test.db")
    Base.metadata.create_all(value.engine)
    yield value
    value.engine.dispose()


@pytest.fixture
def video(tmp_path):
    path = tmp_path / "camera" / "বাংলা স্মৃতি" / "clip.mp4"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + bytes(range(256)) * 64)
    return path
