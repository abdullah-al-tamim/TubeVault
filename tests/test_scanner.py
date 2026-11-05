import os
import time
from sqlalchemy import select
from tubevault.db import Watch, Job, Instance, Mapping
from tubevault.scanner import Scanner


def ready(db, root, **kwargs):
    with db.session() as s:
        s.add(Watch(path=str(root), stability=0, **kwargs))
    Scanner(db).scan()


def test_discovery_unicode_and_duplicate_moves(db, video):
    ready(db, video.parents[1])
    with db.session() as s:
        assert len(list(s.scalars(select(Job)))) == 1
        mapping_id = s.scalar(select(Mapping.id))
    renamed = video.parent.with_name("Renamed collection")
    video.parent.rename(renamed)
    Scanner(db).scan()
    with db.session() as s:
        assert len(list(s.scalars(select(Job)))) == 1
        assert s.scalar(select(Mapping.id)) == mapping_id
        assert any(i.reason.startswith("Duplicate") for i in s.scalars(select(Instance)))


def test_stability_and_modified_content(db, video):
    ready(db, video.parents[1])
    with video.open("ab") as f:
        f.write(b"new footage")
    Scanner(db).scan()
    with db.session() as s:
        assert len(list(s.scalars(select(Job)))) == 2


def test_waits_for_stability(db, video):
    with db.session() as s:
        s.add(Watch(path=str(video.parents[1]), stability=60))
    scanner = Scanner(db)
    scanner.scan()
    with db.session() as s:
        assert not s.scalar(select(Job))
        s.scalar(select(Instance)).stable_since = time.time() - 61
    scanner.scan()
    with db.session() as s:
        assert s.scalar(select(Job))


def test_depth_exclusions_signatures_unsorted(db, video):
    root = video.parents[1]
    (root / "standalone.mp4").write_bytes(video.read_bytes() + b"root")
    (root / "fake.mp4").write_text("not a video")
    (root / "notes.txt").write_text("notes")
    nested = video.parent / "deep"
    nested.mkdir()
    (nested / "nested.mp4").write_bytes(video.read_bytes() + b"deep")
    ready(db, root, depth=1, excludes=["*fake*"], unsorted=True)
    with db.session() as s:
        assert len(list(s.scalars(select(Job)))) == 2
        assert len(list(s.scalars(select(Mapping)))) == 2
        assert not any("nested" in i.path for i in s.scalars(select(Instance)))
        assert any(i.reason == "Unsupported extension" for i in s.scalars(select(Instance)))


def test_inaccessible_watch_is_audited(db, tmp_path):
    ready(db, tmp_path / "missing")
    from tubevault.db import Event
    with db.session() as s:
        assert s.scalar(select(Event)).kind == "scan_error"
