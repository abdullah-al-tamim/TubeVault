import time
import uuid
from contextlib import contextmanager
from sqlalchemy import create_engine, event, String, Integer, Float, Boolean, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def uid():
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)


class Watch(Base):
    __tablename__ = "watch_folders"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    path: Mapped[str] = mapped_column(unique=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    automatic: Mapped[bool] = mapped_column(default=True)
    depth: Mapped[int] = mapped_column(default=8)
    stability: Mapped[int] = mapped_column(default=60)
    unsorted: Mapped[bool] = mapped_column(default=True)
    privacy: Mapped[str] = mapped_column(default="private")
    excludes: Mapped[list] = mapped_column(JSON, default=list)
    max_bytes: Mapped[int] = mapped_column(default=256_000_000_000)


class Mapping(Base):
    __tablename__ = "playlist_mappings"
    __table_args__ = (UniqueConstraint("watch_id", "folder_key"),)
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    watch_id: Mapped[str] = mapped_column(ForeignKey("watch_folders.id"))
    folder_key: Mapped[str]
    path: Mapped[str]
    title: Mapped[str]
    privacy: Mapped[str] = mapped_column(default="private")
    playlist_id: Mapped[str | None]
    account_id: Mapped[str | None]


class Identity(Base):
    __tablename__ = "file_identities"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    sha256: Mapped[str] = mapped_column(unique=True)
    fingerprint: Mapped[str] = mapped_column(index=True)
    size: Mapped[int]


class Instance(Base):
    __tablename__ = "file_instances"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    path: Mapped[str] = mapped_column(unique=True)
    mapping_id: Mapped[str] = mapped_column(ForeignKey("playlist_mappings.id"))
    identity_id: Mapped[str | None] = mapped_column(ForeignKey("file_identities.id"))
    size: Mapped[int]
    mtime_ns: Mapped[int]
    stable_since: Mapped[float] = mapped_column(default=time.time)
    reason: Mapped[str] = mapped_column(default="STABILIZING")


class Job(Base):
    __tablename__ = "upload_jobs"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    identity_id: Mapped[str] = mapped_column(ForeignKey("file_identities.id"), index=True)
    instance_id: Mapped[str] = mapped_column(ForeignKey("file_instances.id"))
    mapping_id: Mapped[str] = mapped_column(ForeignKey("playlist_mappings.id"))
    state: Mapped[str] = mapped_column(default="QUEUED", index=True)
    title: Mapped[str]
    description: Mapped[str] = mapped_column(default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    made_for_kids: Mapped[bool] = mapped_column(default=False)
    privacy: Mapped[str] = mapped_column(default="private")
    video_id: Mapped[str | None]
    account_id: Mapped[str | None]
    progress: Mapped[int] = mapped_column(default=0)
    speed: Mapped[float] = mapped_column(default=0)
    retries: Mapped[int] = mapped_column(default=0)
    next_attempt: Mapped[float] = mapped_column(default=0, index=True)
    claimed: Mapped[bool] = mapped_column(default=False)
    error: Mapped[str] = mapped_column(default="")
    created: Mapped[float] = mapped_column(default=time.time)


class Video(Base):
    __tablename__ = "youtube_videos"
    id: Mapped[str] = mapped_column(primary_key=True)
    identity_id: Mapped[str] = mapped_column(ForeignKey("file_identities.id"), index=True)
    account_id: Mapped[str]
    processing: Mapped[str] = mapped_column(default="processing")
    privacy: Mapped[str]


class UploadSession(Base):
    __tablename__ = "upload_sessions"
    job_id: Mapped[str] = mapped_column(ForeignKey("upload_jobs.id"), primary_key=True)
    secret_key: Mapped[str]
    offset: Mapped[int] = mapped_column(default=0)


class Attempt(Base):
    __tablename__ = "retry_attempts"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey("upload_jobs.id"))
    at: Mapped[float] = mapped_column(default=time.time)
    reason: Mapped[str]


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class Event(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    at: Mapped[float] = mapped_column(default=time.time, index=True)
    kind: Mapped[str]
    message: Mapped[str]
    job_id: Mapped[str | None]


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    at: Mapped[float] = mapped_column(default=time.time)
    message: Mapped[str]
    read: Mapped[bool] = mapped_column(default=False)


class Transfer(Base):
    __tablename__ = "import_transfers"
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    filename: Mapped[str]
    collection: Mapped[str]
    size: Mapped[int]
    offset: Mapped[int] = mapped_column(default=0)
    state: Mapped[str] = mapped_column(default="RECEIVING")
    sha256: Mapped[str | None]
    destination: Mapped[str | None]


DEFAULTS = dict(paused=True, mode="manual", timezone="Asia/Dhaka", start_hour=0, end_hour=6,
                concurrency=1, bandwidth_kbps=0, pause_metered=True, cooldown=0,
                privacy="private", title_template="{filename}", description_template="",
                sort="name", notifications=True)


class Database:
    def __init__(self, path):
        self.engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 30})
        @event.listens_for(self.engine, "connect")
        def setup(conn, _):
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=FULL")
        self.factory = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def session(self):
        with self.factory.begin() as s:
            yield s

    def settings(self):
        with self.session() as s:
            row = s.get(Setting, "app")
            return DEFAULTS | (row.value if row else {})

    def configure(self, values):
        with self.session() as s:
            row = s.get(Setting, "app")
            if row:
                row.value = row.value | values
            else:
                s.add(Setting(key="app", value=DEFAULTS | values))


def transition(s, job, state, message=""):
    previous = job.state
    job.state, job.error = state, message
    s.add(Event(kind="transition", job_id=job.id, message=f"{previous} → {state}: {message}"))
