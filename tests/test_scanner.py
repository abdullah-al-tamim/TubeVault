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

def test_phone_import_does_not_wait_for_unrelated_file_hash(db, video, tmp_path):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from unittest.mock import patch
    from tubevault.imports import Imports
    from tubevault.scanner import digest

    imports = Imports(db, tmp_path / "inbox")
    transfer = imports.create("phone.mov", "Phone", video.stat().st_size)
    imports.append(transfer, 0, video.read_bytes())
    target = imports.finish(transfer)
    with db.session() as session:
        watch = Watch(path=str(video.parents[1]), stability=0)
        session.add(watch)
        session.flush()
        watch_id = watch.id
    scanner = Scanner(db)
    hashing = threading.Event()
    release = threading.Event()

    def blocked_hash(path):
        if str(path) == str(video):
            hashing.set()
            assert release.wait(10)
        return digest(path)

    with patch("tubevault.scanner.digest", side_effect=blocked_hash), ThreadPoolExecutor(max_workers=2) as pool:
        background = pool.submit(scanner.scan, watch_id)
        assert hashing.wait(3)
        try:
            pool.submit(scanner.scan_import, target, imports.root).result(timeout=3)
            assert not release.is_set()
            with db.session() as session:
                assert len(list(session.scalars(select(Job)))) == 1
        finally:
            release.set()
        background.result(timeout=3)


def test_concurrent_same_file_hash_creates_one_job(db, video):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from unittest.mock import patch
    from tubevault.scanner import digest
    with db.session() as session:
        session.add(Watch(path=str(video.parents[1]), stability=0))
    scanner = Scanner(db)
    barrier = threading.Barrier(2)

    def simultaneous_hash(path):
        barrier.wait(timeout=5)
        return digest(path)

    with patch("tubevault.scanner.digest", side_effect=simultaneous_hash), ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(scanner.scan) for _ in range(2)]
        for future in futures:
            future.result(timeout=7)
    with db.session() as session:
        assert len(list(session.scalars(select(Job)))) == 1
