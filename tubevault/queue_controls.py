from sqlalchemy import select
from .db import Job, UploadSession, transition

HOLD = {"pause": "PAUSED", "skip": "SKIPPED", "exclude": "SKIPPED", "cancel": "CANCELLED", "remove": "REMOVED"}

def control_jobs(db, ids, action):
    results = []
    with db.session() as s:
        for job_id in dict.fromkeys(ids):
            job = s.get(Job, job_id)
            error = None
            if not job:
                error = "Video not found"
            elif job.state in {"COMPLETED", "UPLOAD_UNCERTAIN"}:
                error = "Completed videos cannot be changed; uncertain uploads must be reconciled"
            elif job.state == "UPLOADING" and not job.claimed and not s.get(UploadSession, job.id):
                error = "Session initiation outcome unknown; wait for recovery and reconcile"
            elif action in HOLD:
                job.control_requested = HOLD[action]
                # Persist the hold even if the worker is releasing its claim concurrently.
                transition(s, job, HOLD[action], "User action; source and remote video retained")
            elif job.claimed:
                error = "Wait for the current operation to stop before resuming"
            else:
                job.control_requested = ""
                target = "PROCESSING" if job.video_id else "UPLOADING" if s.get(UploadSession, job.id) else "QUEUED"
                transition(s, job, target, "Resumed by user")
                job.next_attempt = 0
            results.append({"id": job_id, "ok": error is None, "error": error})
    return {"results": results}
