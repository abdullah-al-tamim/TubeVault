import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from .db import Database, Watch, Mapping, Job, Instance, Identity, Account, Event, Transfer, Video, UploadSession, transition
from .config import config as default_config
from .security import Security
from .scanner import Scanner
from .imports import Imports

Privacy = Literal["private", "unlisted", "public"]


class Login(BaseModel):
    password: str = Field(max_length=1024)


class WatchInput(BaseModel):
    path: str
    enabled: bool = True
    automatic: bool = True
    depth: int = Field(default=8, ge=0, le=50)
    stability: int = Field(default=60, ge=1, le=86400)
    unsorted: bool = True
    privacy: Privacy = "private"
    excludes: list[str] = Field(default_factory=list, max_length=100)
    max_bytes: int = Field(default=256_000_000_000, gt=0, le=256_000_000_000)


class SettingsInput(BaseModel):
    paused: bool = True
    mode: Literal["manual", "automatic", "scheduled"] = "manual"
    timezone: str = "Asia/Dhaka"
    start_hour: int = Field(default=0, ge=0, le=23)
    end_hour: int = Field(default=6, ge=0, le=23)
    concurrency: int = Field(default=1, ge=1, le=4)
    bandwidth_kbps: int = Field(default=0, ge=0, le=1000000)
    pause_metered: bool = True
    privacy: Privacy = "private"
    title_template: str = Field(default="{filename}", min_length=1, max_length=100)
    description_template: str = Field(default="", max_length=4500)
    sort: Literal["name", "date"] = "name"
    notifications: bool = True


class Metadata(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=4500)
    privacy: Privacy = "private"
    tags: list[str] = Field(default_factory=list, max_length=30)
    made_for_kids: bool = False


class MappingInput(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    privacy: Privacy = "private"
    playlist_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{10,100}$")


class ImportInput(BaseModel):
    filename: str
    collection: str
    size: int


class ReconcileInput(BaseModel):
    video_id: str = Field(pattern=r"^[A-Za-z0-9_-]{11}$")


def rowdict(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


def create_app(config=default_config, db=None, services=None, background=True):
    config.data_dir.mkdir(parents=True, exist_ok=True)
    db = db or Database(config.data_dir / "tubevault.db")
    if len(config.password) < 16:
        raise RuntimeError("Set TUBEVAULT_PASSWORD to at least 16 characters in .env before starting")
    security = Security(config.password, config.origins)
    scanner = Scanner(db)
    imports = Imports(db, config.data_dir / "inbox")
    if services is None:
        from .auth import Auth, Secrets
        from .youtube import YouTube
        from .worker import Worker
        from .scheduler import Scheduler
        secrets = Secrets(config.data_dir)
        auth = Auth(db, secrets, config)
        youtube = YouTube(auth)
        worker = Worker(db, youtube, secrets)
        scheduler = Scheduler(db, scanner, worker)
    else:
        auth, youtube, worker, scheduler = services

    @asynccontextmanager
    async def lifespan(app):
        if background:
            scheduler.start()
        yield
        if background:
            await asyncio.to_thread(scheduler.close)

    app = FastAPI(title="TubeVault", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.allowed_hosts.split(","))

    @app.middleware("http")
    async def protections(request, call_next):
        length = request.headers.get("content-length", "0")
        if not length.isdigit() or int(length) > 8 * 1024 * 1024 + 4096:
            return Response("Request too large", status_code=413)
        response = await call_next(request)
        response.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer", "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"})
        return response

    @app.post("/api/login")
    def login(body: Login, request: Request, response: Response):
        if request.headers.get("origin") not in security.origins:
            raise HTTPException(403, "Origin rejected")
        token, csrf = security.login(request, body.password)
        response.set_cookie("tv_session", token, httponly=True, samesite="strict", secure=config.secure_cookie, max_age=43200)
        return {"csrf": csrf}

    api = APIRouter(prefix="/api", dependencies=[Depends(security.check)])

    @api.get("/session")
    def session(request: Request):
        return {"csrf": security.check(request)}

    @api.post("/logout")
    def logout(request: Request, response: Response):
        security.sessions.pop(request.cookies.get("tv_session"), None)
        response.delete_cookie("tv_session")
        return {"ok": True}

    def snapshot():
        with db.session() as s:
            jobs = []
            for job in s.scalars(select(Job).order_by(Job.created.desc()).limit(2000)):
                item = rowdict(job)
                identity = s.get(Identity, job.identity_id)
                item.update(size=identity.size, sha256=identity.sha256,
                            path=s.get(Instance, job.instance_id).path, playlist=s.get(Mapping, job.mapping_id).title)
                jobs.append(item)
            account = s.scalar(select(Account))
            counts = dict(s.execute(select(Job.state, func.count()).group_by(Job.state)).all())
            stats = {"discovered": s.scalar(select(func.count()).select_from(Instance)),
                     "archived": counts.get("COMPLETED", 0),
                     "queued": sum(counts.get(k, 0) for k in ("QUEUED", "PAUSED", "UPLOADING", "PROCESSING", "PLAYLIST_PENDING")),
                     "failed": sum(counts.get(k, 0) for k in ("FAILED_RETRYABLE", "FAILED_PERMANENT", "UPLOAD_UNCERTAIN")),
                     "bytes": s.scalar(select(func.coalesce(func.sum(Identity.size), 0)).join(Job, Job.identity_id == Identity.id).where(Job.state == "COMPLETED"))}
            return {"stats": stats, "jobs": jobs, "watches": [rowdict(w) for w in s.scalars(select(Watch))],
                    "mappings": [rowdict(m) for m in s.scalars(select(Mapping))],
                    "instances": [rowdict(i) for i in s.scalars(select(Instance).limit(2000))],
                    "events": [rowdict(e) for e in s.scalars(select(Event).order_by(Event.at.desc()).limit(100))],
                    "imports": [rowdict(t) for t in s.scalars(select(Transfer))],
                    "account": rowdict(account) | {"connected": auth.connected()} if account else None, "settings": db.settings()}

    @api.get("/snapshot")
    def get_snapshot():
        return snapshot()

    @api.get("/events")
    async def events(request: Request):
        async def stream():
            while not await request.is_disconnected():
                try:
                    security.check(request)
                except HTTPException:
                    return
                yield "data: " + json.dumps(await asyncio.to_thread(snapshot)) + "\n\n"
                await asyncio.sleep(2)
        return StreamingResponse(stream(), media_type="text/event-stream")

    @api.post("/watches")
    def add_watch(body: WatchInput):
        try:
            path = Path(body.path).resolve(strict=True)
        except OSError:
            raise HTTPException(400, "Directory is unavailable; check its path and drive connection") from None
        if not path.is_dir():
            raise HTTPException(400, "Choose an existing directory")
        with db.session() as s:
            if s.scalar(select(Watch).where(Watch.path == str(path))):
                raise HTTPException(409, "Already watched")
            row = Watch(**(body.model_dump() | {"path": str(path)}))
            s.add(row)
            s.flush()
            return rowdict(row)

    @api.put("/watches/{watch_id}")
    def edit_watch(watch_id: str, body: WatchInput):
        with db.session() as s:
            row = s.get(Watch, watch_id)
            if not row:
                raise HTTPException(404)
            # Preserve identity and history; changing root is a separate add operation.
            if str(Path(body.path).resolve()) != row.path:
                raise HTTPException(400, "Add a new watch root instead")
            for key, value in body.model_dump().items():
                setattr(row, key, value)
            return rowdict(row)

    @api.post("/scan")
    def scan():
        scanner.scan()
        return {"ok": True}

    @api.put("/settings")
    def settings(body: SettingsInput):
        try:
            ZoneInfo(body.timezone)
        except Exception:
            raise HTTPException(400, "Unknown timezone") from None
        db.configure(body.model_dump())
        return db.settings()

    @api.post("/queue/{action}")
    def queue(action: Literal["pause", "resume"]):
        db.configure({"paused": action == "pause"})
        return db.settings()

    @api.post("/jobs/{job_id}/{action}")
    def control(job_id: str, action: Literal["pause", "resume", "retry", "exclude", "force"]):
        with db.session() as s:
            job = s.get(Job, job_id)
            if not job:
                raise HTTPException(404)
            if job.claimed:
                raise HTTPException(409, "Pause the queue and wait for the current chunk to finish")
            if job.state == "UPLOAD_UNCERTAIN":
                raise HTTPException(409, "Reconcile the uncertain upload with a verified video ID")
            if action == "force":
                if job.state != "COMPLETED":
                    raise HTTPException(409, "Only completed uploads may be explicitly duplicated")
                new = Job(identity_id=job.identity_id, instance_id=job.instance_id, mapping_id=job.mapping_id,
                          title=job.title, description=job.description, privacy=job.privacy, tags=job.tags, made_for_kids=job.made_for_kids)
                s.add(new)
                return {"ok": True}
            if job.state == "COMPLETED":
                raise HTTPException(409, "Already completed")
            target = {"pause": "PAUSED", "exclude": "SKIPPED"}.get(action)
            if not target:
                target = "PROCESSING" if job.video_id else "UPLOADING" if s.get(UploadSession, job.id) else "QUEUED"
            transition(s, job, target, "User action")
            job.next_attempt = 0
            return {"ok": True}

    @api.put("/jobs/{job_id}/metadata")
    def metadata(job_id: str, body: Metadata):
        with db.session() as s:
            job = s.get(Job, job_id)
            if not job:
                raise HTTPException(404)
            if job.claimed or job.video_id or job.state not in {"QUEUED", "PAUSED"}:
                raise HTTPException(409, "Metadata is locked after upload begins")
            for key, value in body.model_dump().items():
                setattr(job, key, value)
            return {"ok": True}

    @api.post("/jobs/{job_id}/reconcile")
    def reconcile(job_id: str, body: ReconcileInput):
        video = youtube.video(body.video_id)
        with db.session() as s:
            job, account = s.get(Job, job_id), s.scalar(select(Account))
            if not job or job.state != "UPLOAD_UNCERTAIN" or job.claimed:
                raise HTTPException(409, "Job is not awaiting reconciliation")
            if not account or video["snippet"]["channelId"] != account.id or ("TubeVault job " + job.id) not in video["snippet"].get("description", ""):
                raise HTTPException(400, "Video does not match this channel and job marker")
            job.video_id = body.video_id
            s.merge(Video(id=body.video_id, identity_id=job.identity_id, account_id=account.id, privacy=video["status"]["privacyStatus"]))
            transition(s, job, "PROCESSING", "Verified user reconciliation")
            return {"ok": True}

    @api.put("/mappings/{mapping_id}")
    def mapping(mapping_id: str, body: MappingInput):
        if body.playlist_id:
            if body.playlist_id not in {p["id"] for p in youtube.playlists()}:
                raise HTTPException(400, "Playlist not owned by connected account")
        with db.session() as s:
            row = s.get(Mapping, mapping_id)
            if not row:
                raise HTTPException(404)
            row.title, row.privacy = body.title, body.privacy
            if body.playlist_id:
                row.playlist_id = body.playlist_id
            return rowdict(row)

    @api.post("/account/connect")
    def connect(request: Request):
        if request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            raise HTTPException(403, "Connect from the Windows PC")
        try:
            auth.connect()
        except Exception as e:
            raise HTTPException(400, "Google connection failed: " + type(e).__name__) from None
        return {"ok": True}

    @api.post("/account/disconnect")
    def disconnect():
        auth.disconnect()
        return {"ok": True}

    @api.post("/imports")
    def create_import(body: ImportInput):
        try:
            return {"id": imports.create(body.filename, body.collection, body.size)}
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @api.get("/imports/{transfer_id}")
    def get_import(transfer_id: str):
        with db.session() as s:
            row = s.get(Transfer, transfer_id)
            if not row:
                raise HTTPException(404)
            return rowdict(row)

    @api.put("/imports/{transfer_id}")
    async def chunk(transfer_id: str, offset: int, request: Request):
        body = bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body) > 8 * 1024 * 1024:
                raise HTTPException(413)
        try:
            return {"offset": await asyncio.to_thread(imports.append, transfer_id, offset, bytes(body))}
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @api.post("/imports/{transfer_id}/finish")
    def finish(transfer_id: str):
        try:
            destination = imports.finish(transfer_id)
            scanner.scan()
            return {"destination": destination}
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    app.include_router(api)
    dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"

    @app.get("/{path:path}")
    def frontend(path: str):
        candidate = (dist / path).resolve()
        if not candidate.is_relative_to(dist.resolve()) or path.startswith("api/"):
            raise HTTPException(404)
        if candidate.is_file():
            return FileResponse(candidate)
        if (dist / "index.html").exists():
            return FileResponse(dist / "index.html")
        return {"message": "Build frontend with npm run build in frontend/"}

    return app
