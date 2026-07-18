from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, create_engine, delete, event, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .mikan import Bangumi


def _configure_sqlite(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Base(DeclarativeBase):
    pass


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    poster_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReleaseRecord(Base):
    __tablename__ = "releases"
    id: Mapped[int] = mapped_column(primary_key=True)
    guid: Mapped[str] = mapped_column(String(1000), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(1000))
    torrent_url: Mapped[str] = mapped_column(String(1000))
    score: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="发现")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DownloadTask(Base):
    __tablename__ = "download_tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    release_id: Mapped[int | None] = mapped_column(ForeignKey("releases.id"), nullable=True)
    info_hash: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    title: Mapped[str] = mapped_column(String(1000))
    save_path: Mapped[str] = mapped_column(String(1000))
    working_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    state: Mapped[str] = mapped_column(String(40), default="等待中")
    progress: Mapped[float] = mapped_column(Float, default=0)
    download_rate: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CatalogEntry(Base):
    __tablename__ = "catalog_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    url: Mapped[str] = mapped_column(String(1000))
    poster_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(String(2000))


class DanmakuEntry(Base):
    __tablename__ = "danmaku_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    media_id: Mapped[str] = mapped_column(String(80), index=True)
    time: Mapped[float] = mapped_column(Float)
    type: Mapped[int] = mapped_column(Integer, default=0)
    color: Mapped[int] = mapped_column(Integer, default=16777215)
    author: Mapped[str] = mapped_column(String(60), default="local")
    text: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WatchProgress(Base):
    __tablename__ = "watch_progress"
    media_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    position: Mapped[float] = mapped_column(Float, default=0)
    duration: Mapped[float] = mapped_column(Float, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HiddenMedia(Base):
    __tablename__ = "hidden_media"
    relative_path: Mapped[str] = mapped_column(String(1000), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(500))
    message: Mapped[str] = mapped_column(String(1000))
    link: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class TaskHealth(Base):
    __tablename__ = "task_health"
    task_id: Mapped[int] = mapped_column(
        ForeignKey("download_tasks.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    peer_count: Mapped[int] = mapped_column(Integer, default=0)
    seed_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40), default="连接中")
    last_progress: Mapped[float] = mapped_column(Float, default=0)
    last_progress_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    switch_count: Mapped[int] = mapped_column(Integer, default=0)
    attempted_guids: Mapped[str] = mapped_column(String(8000), default="[]")

    @property
    def attempted_guid_list(self) -> list[str]:
        try:
            value = json.loads(self.attempted_guids)
        except (TypeError, json.JSONDecodeError):
            return []
        return [str(item) for item in value] if isinstance(value, list) else []


class MediaState(Base):
    __tablename__ = "media_states"
    media_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    watched: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Store:
    def __init__(self, database_url: str) -> None:
        is_sqlite = database_url.startswith("sqlite")
        connect_args = {"check_same_thread": False} if is_sqlite else {}
        self.engine = create_engine(database_url, connect_args=connect_args)
        if is_sqlite:
            event.listen(self.engine, "connect", _configure_sqlite)

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)
        if self.engine.dialect.name == "sqlite":
            with self.engine.begin() as connection:
                columns = {
                    row[1]
                    for row in connection.exec_driver_sql(
                        "PRAGMA table_info(download_tasks)"
                    )
                }
                if "working_path" not in columns:
                    connection.exec_driver_sql(
                        "ALTER TABLE download_tasks ADD COLUMN working_path VARCHAR(1000)"
                    )

    def subscribe(self, source_id: str, title: str, poster_url: str | None) -> Subscription:
        with Session(self.engine) as session:
            existing = session.scalar(select(Subscription).where(Subscription.source_id == source_id))
            if existing:
                existing.enabled = True
                existing.title = title
                existing.poster_url = poster_url
                result = existing
            else:
                result = Subscription(source_id=source_id, title=title, poster_url=poster_url)
                session.add(result)
            session.commit()
            session.refresh(result)
            session.expunge(result)
            return result

    def unsubscribe(self, source_id: str) -> None:
        with Session(self.engine) as session:
            item = session.scalar(select(Subscription).where(Subscription.source_id == source_id))
            if item:
                item.enabled = False
                session.commit()

    def list_subscriptions(self) -> list[Subscription]:
        with Session(self.engine) as session:
            items = list(session.scalars(select(Subscription).order_by(Subscription.created_at.desc())))
            session.expunge_all()
            return items

    def record_release(self, guid: str, title: str, torrent_url: str, score: int = 0) -> tuple[ReleaseRecord, bool]:
        with Session(self.engine) as session:
            existing = session.scalar(select(ReleaseRecord).where(ReleaseRecord.guid == guid))
            if existing:
                session.expunge(existing)
                return existing, False
            item = ReleaseRecord(guid=guid, title=title, torrent_url=torrent_url, score=score)
            session.add(item)
            session.commit()
            session.refresh(item)
            session.expunge(item)
            return item, True

    def create_task(
        self,
        title: str,
        save_path: str,
        release_id: int | None = None,
        working_path: str | None = None,
    ) -> DownloadTask:
        with Session(self.engine) as session:
            item = DownloadTask(
                title=title,
                save_path=save_path,
                release_id=release_id,
                working_path=working_path,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            session.expunge(item)
            return item

    def list_tasks(self) -> list[DownloadTask]:
        with Session(self.engine) as session:
            items = list(session.scalars(select(DownloadTask).order_by(DownloadTask.created_at.desc())))
            session.expunge_all()
            return items

    def update_task(self, task_id: int, **values: object) -> None:
        with Session(self.engine) as session:
            item = session.get(DownloadTask, task_id)
            if item:
                for key, value in values.items():
                    setattr(item, key, value)
                session.commit()

    def delete_task(self, task_id: int) -> None:
        with Session(self.engine) as session:
            health = session.get(TaskHealth, task_id)
            if health:
                session.delete(health)
            item = session.get(DownloadTask, task_id)
            if item:
                session.delete(item)
                session.commit()

    def replace_catalog(self, items: list[Bangumi]) -> None:
        refreshed_at = datetime.utcnow()
        with Session(self.engine) as session:
            session.execute(delete(CatalogEntry))
            session.add_all(
                CatalogEntry(
                    source_id=item.source_id,
                    title=item.title,
                    url=item.url,
                    poster_url=item.poster_url,
                    refreshed_at=refreshed_at,
                )
                for item in items
            )
            session.commit()

    def list_catalog(self, query: str = "") -> list[Bangumi]:
        statement = select(CatalogEntry).order_by(CatalogEntry.title)
        if query:
            statement = statement.where(CatalogEntry.title.contains(query))
        with Session(self.engine) as session:
            items = list(session.scalars(statement))
            return [Bangumi(item.source_id, item.title, item.url, item.poster_url) for item in items]

    def catalog_updated_at(self) -> datetime | None:
        with Session(self.engine) as session:
            return session.scalar(select(func.max(CatalogEntry.refreshed_at)))

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with Session(self.engine) as session:
            item = session.get(Setting, key)
            return item.value if item else default

    def set_setting(self, key: str, value: str) -> None:
        with Session(self.engine) as session:
            item = session.get(Setting, key)
            if item:
                item.value = value
            else:
                session.add(Setting(key=key, value=value))
            session.commit()

    def add_danmaku(self, media_id: str, time: float, type_: int, color: int, author: str, text: str) -> None:
        with Session(self.engine) as session:
            session.add(DanmakuEntry(media_id=media_id, time=time, type=type_, color=color, author=author, text=text))
            session.commit()

    def list_danmaku(self, media_id: str) -> list[DanmakuEntry]:
        with Session(self.engine) as session:
            items = list(session.scalars(select(DanmakuEntry).where(DanmakuEntry.media_id == media_id).order_by(DanmakuEntry.time)))
            session.expunge_all()
            return items

    def delete_danmaku(self, danmaku_id: int, media_id: str) -> bool:
        with Session(self.engine) as session:
            item = session.get(DanmakuEntry, danmaku_id)
            if item is None or item.media_id != media_id:
                return False
            session.delete(item)
            session.commit()
            return True

    def clear_danmaku(self, media_id: str) -> int:
        with Session(self.engine) as session:
            result = session.execute(delete(DanmakuEntry).where(DanmakuEntry.media_id == media_id))
            session.commit()
            return result.rowcount or 0

    def save_progress(self, media_id: str, position: float, duration: float) -> None:
        with Session(self.engine) as session:
            item = session.get(WatchProgress, media_id)
            if item:
                item.position, item.duration, item.updated_at = position, duration, datetime.utcnow()
            else:
                session.add(WatchProgress(media_id=media_id, position=position, duration=duration))
            session.commit()

    def get_progress(self, media_id: str) -> WatchProgress | None:
        with Session(self.engine) as session:
            item = session.get(WatchProgress, media_id)
            if item:
                session.expunge(item)
            return item

    def set_media_watched(self, media_id: str, watched: bool) -> None:
        with Session(self.engine) as session:
            item = session.get(MediaState, media_id)
            if item:
                item.watched = watched
                item.updated_at = datetime.utcnow()
            else:
                session.add(MediaState(media_id=media_id, watched=watched))
            session.commit()

    def is_media_watched(self, media_id: str) -> bool:
        with Session(self.engine) as session:
            item = session.get(MediaState, media_id)
            return bool(item and item.watched)

    def list_watched_media(self) -> set[str]:
        with Session(self.engine) as session:
            return set(
                session.scalars(select(MediaState.media_id).where(MediaState.watched.is_(True)))
            )

    def update_task_health(self, task_id: int, **values: object) -> None:
        with Session(self.engine) as session:
            item = session.get(TaskHealth, task_id)
            if item is None:
                item = TaskHealth(task_id=task_id)
                session.add(item)
            for key, value in values.items():
                if key == "attempted_guids":
                    value = json.dumps(value, ensure_ascii=False)
                setattr(item, key, value)
            session.commit()

    def get_task_health(self, task_id: int) -> TaskHealth | None:
        with Session(self.engine) as session:
            item = session.get(TaskHealth, task_id)
            if item:
                session.expunge(item)
            return item

    def list_task_health(self) -> dict[int, TaskHealth]:
        with Session(self.engine) as session:
            items = list(session.scalars(select(TaskHealth)))
            session.expunge_all()
            return {item.task_id: item for item in items}

    def add_notification(
        self, kind: str, title: str, message: str, link: str | None = None
    ) -> Notification:
        with Session(self.engine) as session:
            item = Notification(kind=kind, title=title, message=message, link=link)
            session.add(item)
            session.commit()
            session.refresh(item)
            session.expunge(item)
            return item

    def list_notifications(self, limit: int = 100) -> list[Notification]:
        with Session(self.engine) as session:
            items = list(
                session.scalars(
                    select(Notification).order_by(Notification.created_at.desc()).limit(limit)
                )
            )
            session.expunge_all()
            return items

    def unread_notification_count(self) -> int:
        with Session(self.engine) as session:
            return int(
                session.scalar(
                    select(func.count()).select_from(Notification).where(Notification.read.is_(False))
                )
                or 0
            )

    def mark_notifications_read(self) -> None:
        with Session(self.engine) as session:
            for item in session.scalars(select(Notification).where(Notification.read.is_(False))):
                item.read = True
            session.commit()

    def clear_notifications(self) -> None:
        with Session(self.engine) as session:
            session.execute(delete(Notification))
            session.commit()

    def hide_media(self, relative_path: str) -> None:
        with Session(self.engine) as session:
            if session.get(HiddenMedia, relative_path) is None:
                session.add(HiddenMedia(relative_path=relative_path))
                session.commit()

    def restore_media(self, relative_path: str) -> None:
        with Session(self.engine) as session:
            item = session.get(HiddenMedia, relative_path)
            if item:
                session.delete(item)
                session.commit()

    def list_hidden_media(self) -> list[str]:
        with Session(self.engine) as session:
            return list(
                session.scalars(
                    select(HiddenMedia.relative_path).order_by(HiddenMedia.created_at.desc())
                )
            )
