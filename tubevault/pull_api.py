from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field


class PullInput(BaseModel):
    url: str = Field(min_length=1, max_length=4096)
    format: str = "source"
    height: int | None = None


def pull_routes(service):
    router = APIRouter(prefix="/pulls")

    @router.get("")
    def recent():
        return service.recent()

    @router.post("", status_code=202)
    def start(body: PullInput, tasks: BackgroundTasks):
        try:
            record, lock = service.prepare(body.url, body.format, body.height)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        tasks.add_task(service.finish, record, lock)
        return record

    @router.get("/{key}/file")
    def file(key: UUID):
        folder = service.root / key.hex
        if not (folder / "status.json").is_file():
            raise HTTPException(404, "Pull not found.")
        record = service.get(folder)
        if record["state"] != "Ready":
            raise HTTPException(409, "Pull is not ready.")
        path = Path(record["path"]).resolve()
        if path.parent != folder or not path.is_file():
            raise HTTPException(404, "The local file is missing.")
        return FileResponse(path, filename=path.name)

    return router
