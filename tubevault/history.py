from .db import Event, Job


def control_history(db, ids, action):
    results = []
    with db.session() as s:
        for job_id in dict.fromkeys(ids):
            job = s.get(Job, job_id)
            error = None
            if not job:
                error = "Video not found"
            elif job.state != "COMPLETED" or job.claimed:
                error = "Only completed, inactive archive entries can be changed"
            elif job.history_hidden != (action == "remove"):
                job.history_hidden = action == "remove"
                s.add(Event(kind="history_visibility", job_id=job_id,
                            message=f"Archive entry {action}; source, remote video and upload evidence retained"))
            results.append({"id": job_id, "ok": error is None, "error": error})
    return {"results": results}
