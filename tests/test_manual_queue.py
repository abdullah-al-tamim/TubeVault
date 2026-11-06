import os
import time
from sqlalchemy import select
from tubevault.db import Job, Watch
from tubevault.scanner import Scanner
from tubevault.queue_controls import control_jobs

def test_manual_files_only_selected_and_restore(db, video):
    os.utime(video, (time.time()-120,time.time()-120))
    sibling=video.with_name("other.mp4")
    sibling.write_bytes(video.read_bytes()+b"other")
    scanner=Scanner(db)
    assert scanner.add_files([str(video)])["results"][0]["ok"]
    scanner.scan(automatic=True)
    with db.session() as s:
        jobs=list(s.scalars(select(Job)))
        assert len(jobs)==1
        assert not s.scalar(select(Watch)).enabled
        job_id=jobs[0].id
    control_jobs(db,[job_id],"remove")
    assert scanner.add_files([str(video)])["results"][0]["ok"]
    with db.session() as s:
        assert s.get(Job,job_id).state=="QUEUED"
        assert len(list(s.scalars(select(Job))))==1

def test_recent_manual_file_rejected(db,video):
    assert not Scanner(db).add_files([str(video)])["results"][0]["ok"]
