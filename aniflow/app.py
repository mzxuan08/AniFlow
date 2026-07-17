from __future__ import annotations

import os
import shutil
import hashlib
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from starlette.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .downloader import DisabledEngine, LibtorrentEngine
from .library import resolve_media_path, scan_library
from .matching import classify_release, extract_episode, release_version, select_latest_1080p
from .mikan import Bangumi, MikanClient
from .poster_cache import cache_catalog_posters, find_cached_poster
from .store import Store
from .settings import has_minimum_free_space, validate_download_directory

PACKAGE_DIR = Path(__file__).parent
DEFAULT_DATA_DIR = Path(os.getenv("ANIFLOW_DATA_DIR", "data")).resolve()
DEFAULT_DOWNLOAD_DIR = Path(os.getenv("ANIFLOW_DOWNLOAD_DIR", "downloads")).resolve()


class CachedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: dict[str, Any]) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code in {200, 304}:
            response.headers["Cache-Control"] = "public, max-age=3600"
        return response


class DanmakuPayload(BaseModel):
    id: str
    author: str = "local"
    time: float
    text: str
    color: int = 16777215
    type: int = 0


class ProgressPayload(BaseModel):
    position: float
    duration: float


def create_app(
    database_url: str | None = None,
    mikan_client: Any | None = None,
    engine: Any | None = None,
    poster_cacher: Any | None = None,
) -> FastAPI:
    data_dir = DEFAULT_DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    store = Store(database_url or f"sqlite:///{data_dir / 'aniflow.db'}")
    store.create_schema()
    mikan = mikan_client or MikanClient()
    bt = engine or (
        DisabledEngine() if database_url else LibtorrentEngine(data_dir / "bt", store.update_task)
    )
    scheduler = AsyncIOScheduler()
    poster_dir = data_dir / "posters"
    poster_dir.mkdir(parents=True, exist_ok=True)
    cache_posters = poster_cacher or cache_catalog_posters

    def download_root() -> Path:
        return Path(store.get_setting("download_dir", str(DEFAULT_DOWNLOAD_DIR)) or DEFAULT_DOWNLOAD_DIR)

    def download_space_available() -> bool:
        minimum = float(store.get_setting("min_free_gb", "2") or 2)
        return has_minimum_free_space(download_root(), minimum)

    def replace_lower_version_tasks(save_path: Path, episode: int, version: int) -> bool:
        tasks = [
            task
            for task in store.list_tasks()
            if Path(task.save_path) == save_path
            and extract_episode(task.title)[1] == episode
        ]
        if any(release_version(task.title) >= version for task in tasks):
            return False
        for task in tasks:
            if task.state == "已完成":
                continue
            bt.remove(task.id, delete_files=True)
            store.delete_task(task.id)
        return True

    async def refresh_releases() -> int:
        subscriptions = [s for s in store.list_subscriptions() if s.enabled]
        if not subscriptions:
            return 0
        if not download_space_available():
            return 0
        releases = await mikan.rss()
        candidates: dict[tuple[str, int | None, int], list[tuple[Any, Any, Any]]] = {}
        for release in releases:
            if "1080p" not in release.title.casefold():
                continue
            match = classify_release(release.title)
            if not match.accepted:
                continue
            normalized = release.title.casefold().replace(" ", "")
            subscription = next(
                (s for s in subscriptions if _title_matches(s.title, normalized)), None
            )
            if subscription is None:
                continue
            season, episode = extract_episode(release.title)
            if episode is None:
                continue
            candidates.setdefault((subscription.source_id, season, episode), []).append(
                (subscription, release, match)
            )
        created_count = 0
        for (_source_id, season, episode), items in candidates.items():
            subscription, release, match = max(
                items,
                key=lambda item: (release_version(item[1].title), item[2].score),
            )
            save_path = download_root() / _safe_name(subscription.title)
            if season:
                save_path /= f"Season {season:02d}"
            if not replace_lower_version_tasks(
                save_path, episode, release_version(release.title)
            ):
                continue
            record, created = store.record_release(
                release.guid, release.title, release.torrent_url, match.score
            )
            if not created:
                continue
            created_count += 1
            task = store.create_task(release.title, str(save_path), record.id)
            try:
                torrent_data = await mikan.torrent(release.torrent_url)
                bt.add_torrent(task.id, torrent_data, save_path)
            except Exception as exc:
                store.update_task(task.id, state="错误", error=str(exc))
        return created_count

    async def refresh_catalog() -> int:
        items = await mikan.catalog()
        store.replace_catalog(items)
        asyncio.create_task(cache_posters(items, poster_dir))
        return len(items)

    async def download_latest(source_id: str, title: str) -> str:
        try:
            selected = select_latest_1080p(await mikan.bangumi_releases(source_id))
        except Exception:
            return "error"
        if selected is None:
            return "no_match"
        if not download_space_available():
            return "no_space"
        match = classify_release(selected.title)
        record, created = store.record_release(
            selected.guid, selected.title, selected.torrent_url, match.score
        )
        if not created:
            return "exists"
        season, _episode = extract_episode(selected.title)
        save_path = download_root() / _safe_name(title)
        if season:
            save_path /= f"Season {season:02d}"
        if _episode is not None and not replace_lower_version_tasks(
            save_path, _episode, release_version(selected.title)
        ):
            return "exists"
        task = store.create_task(selected.title, str(save_path), record.id)
        try:
            torrent_data = await mikan.torrent(selected.torrent_url)
            bt.add_torrent(task.id, torrent_data, save_path)
        except Exception as exc:
            store.update_task(task.id, state="错误", error=str(exc))
            return "error"
        return "started"

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        bt.configure(
            int(store.get_setting("max_downloads", "3") or 3),
            int(store.get_setting("download_limit_kbps", "0") or 0),
            int(store.get_setting("upload_limit_kbps", "0") or 0),
        )
        for task in store.list_tasks():
            if task.state not in {"已完成", "错误"}:
                try:
                    bt.restore(task.id, Path(task.save_path))
                except Exception as exc:
                    store.update_task(task.id, state="错误", error=str(exc))
        scheduler.add_job(refresh_releases, "interval", minutes=10, id="rss", replace_existing=True)
        scheduler.add_job(refresh_catalog, "interval", hours=6, id="catalog", replace_existing=True)
        scheduler.start()
        try:
            yield
        finally:
            scheduler.shutdown(wait=False)
            close_mikan = getattr(mikan, "aclose", None)
            if callable(close_mikan):
                await close_mikan()

    app = FastAPI(title="AniFlow", lifespan=lifespan)
    app.state.store = store
    app.state.mikan = mikan
    app.state.bt = bt
    app.state.refresh_releases = refresh_releases
    app.state.refresh_catalog = refresh_catalog
    app.state.poster_dir = poster_dir
    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")
    static_files = CachedStaticFiles(directory=PACKAGE_DIR / "static")
    app.mount(
        "/static",
        GZipMiddleware(static_files, minimum_size=1024, compresslevel=6),
        name="static",
    )

    def context(request: Request, **values: Any) -> dict[str, Any]:
        return {"request": request, "bt": bt, **values}

    def incomplete_media_files() -> set[Path]:
        getter = getattr(bt, "incomplete_files", None)
        if not callable(getter):
            return set()
        try:
            return {Path(path).resolve() for path in getter()}
        except Exception:
            return set()

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            context(request, subscriptions=store.list_subscriptions(), tasks=store.list_tasks()),
        )

    @app.get("/discover", response_class=HTMLResponse)
    async def discover(request: Request, q: str = "", refreshed: int = 0):
        error = None
        items: list[Bangumi] = store.list_catalog(q)
        if not items and not q and store.catalog_updated_at() is None:
            try:
                await refresh_catalog()
                items = store.list_catalog()
            except Exception as exc:
                error = str(exc)
        subscribed = {s.source_id for s in store.list_subscriptions() if s.enabled}
        return templates.TemplateResponse(
            request,
            "discover.html",
            context(
                request,
                items=items,
                q=q,
                subscribed=subscribed,
                error=error,
                updated_at=store.catalog_updated_at(),
                refreshed=refreshed,
            ),
        )

    @app.post("/discover/refresh")
    async def refresh_discover():
        await refresh_catalog()
        return RedirectResponse("/discover?refreshed=1", status_code=303)

    @app.get("/posters/{source_id}")
    async def poster(source_id: str):
        cached = find_cached_poster(poster_dir, source_id)
        if cached is not None:
            return FileResponse(cached, headers={"Cache-Control": "public, max-age=86400"})
        placeholder = """<svg xmlns="http://www.w3.org/2000/svg" width="400" height="560" viewBox="0 0 400 560"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#dcecf1"/><stop offset="1" stop-color="#dfe6f8"/></linearGradient></defs><rect width="400" height="560" fill="url(#g)"/><circle cx="200" cy="250" r="48" fill="#fff" opacity=".6"/><path d="M181 226h38v48h-38z" fill="#39a7aa" opacity=".65"/></svg>"""
        return Response(
            placeholder,
            media_type="image/svg+xml",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/subscriptions", response_class=HTMLResponse)
    async def subscriptions(request: Request, result: str = ""):
        return templates.TemplateResponse(
            request,
            "subscriptions.html",
            context(request, items=store.list_subscriptions(), result=result),
        )

    @app.post("/subscriptions")
    async def subscribe(
        source_id: str = Form(...), title: str = Form(...), poster_url: str = Form("")
    ):
        store.subscribe(source_id, title, poster_url or None)
        result = await download_latest(source_id, title)
        return RedirectResponse(f"/subscriptions?result={result}", status_code=303)

    @app.post("/subscriptions/{source_id}/refresh")
    async def refresh_subscription(source_id: str):
        subscription = next(
            (item for item in store.list_subscriptions() if item.source_id == source_id), None
        )
        if subscription is None:
            raise HTTPException(404)
        result = await download_latest(source_id, subscription.title)
        return RedirectResponse(f"/subscriptions?result={result}", status_code=303)

    @app.post("/subscriptions/{source_id}/delete")
    async def unsubscribe(source_id: str):
        store.unsubscribe(source_id)
        return RedirectResponse("/subscriptions", status_code=303)

    @app.post("/refresh")
    async def refresh():
        await refresh_releases()
        return RedirectResponse("/", status_code=303)

    @app.get("/tasks", response_class=HTMLResponse)
    async def tasks(request: Request, error: str = ""):
        return templates.TemplateResponse(
            request, "tasks.html", context(request, tasks=store.list_tasks(), error=error)
        )

    @app.post("/tasks/{task_id}/pause")
    async def pause_task(task_id: int):
        bt.pause(task_id)
        store.update_task(task_id, state="暂停")
        return RedirectResponse("/tasks", status_code=303)

    @app.post("/tasks/{task_id}/resume")
    async def resume_task(task_id: int):
        bt.resume(task_id)
        store.update_task(task_id, state="下载中")
        return RedirectResponse("/tasks", status_code=303)

    @app.post("/tasks/{task_id}/retry")
    async def retry_task(task_id: int):
        task = next((item for item in store.list_tasks() if item.id == task_id), None)
        if task is None:
            raise HTTPException(404)
        bt.restore(task_id, Path(task.save_path))
        bt.resume(task_id)
        store.update_task(task_id, state="下载中", error=None)
        return RedirectResponse("/tasks", status_code=303)

    @app.post("/tasks/{task_id}/delete")
    async def delete_task(task_id: int, delete_files: bool = Form(False)):
        task = next((item for item in store.list_tasks() if item.id == task_id), None)
        if task is None:
            raise HTTPException(404)
        if task.state == "已完成":
            bt.restore(task_id, Path(task.save_path))
        bt.remove(task_id, delete_files)
        store.delete_task(task_id)
        return RedirectResponse("/tasks", status_code=303)

    @app.post("/tasks/manual")
    async def manual_task(title: str = Form(...), torrent_url: str = Form(...)):
        if not download_space_available():
            return RedirectResponse("/tasks?error=no_space", status_code=303)
        match = classify_release(title)
        release, _ = store.record_release(torrent_url, title, torrent_url, match.score)
        season, episode = extract_episode(title)
        folder = _safe_name(title.split("[")[0])
        if season:
            folder = f"{folder}/Season {season:02d}"
        task = store.create_task(title, str(download_root() / folder), release.id)
        try:
            torrent_data = await mikan.torrent(torrent_url)
            bt.add_torrent(task.id, torrent_data, Path(task.save_path))
        except Exception as exc:
            store.update_task(task.id, state="错误", error=str(exc))
        return RedirectResponse("/tasks", status_code=303)

    @app.get("/library", response_class=HTMLResponse)
    async def library(request: Request, result: str = ""):
        root = download_root()
        groups = scan_library(
            root,
            hidden=set(store.list_hidden_media()),
            unavailable=incomplete_media_files(),
        )
        return templates.TemplateResponse(
            request, "library.html", context(request, groups=groups, result=result)
        )

    @app.post("/library/remove")
    async def remove_library_media(
        relative_path: str = Form(...), delete_file: bool = Form(False)
    ):
        root = download_root().resolve()
        try:
            target = resolve_media_path(root, relative_path)
        except ValueError:
            raise HTTPException(404) from None
        if not target.is_file() or target.suffix.lower() not in {".mp4", ".mkv", ".webm", ".avi"}:
            raise HTTPException(404)
        normalized = target.relative_to(root).as_posix()
        if delete_file:
            try:
                target.unlink()
            except PermissionError:
                return RedirectResponse("/library?result=permission_error", status_code=303)
            store.restore_media(normalized)
            parent = target.parent
            try:
                while parent != root and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
            except OSError:
                pass
            result = "deleted"
        else:
            store.hide_media(normalized)
            result = "hidden"
        return RedirectResponse(f"/library?result={result}", status_code=303)

    @app.get("/media/{relative_path:path}")
    async def media(relative_path: str):
        root = download_root().resolve()
        target = (root / relative_path).resolve()
        if root not in target.parents or not target.is_file():
            raise HTTPException(404)
        if target in incomplete_media_files():
            raise HTTPException(409, "视频仍在下载，完成后即可播放")
        return FileResponse(target)

    @app.get("/watch/{relative_path:path}", response_class=HTMLResponse)
    async def watch(request: Request, relative_path: str):
        root = download_root().resolve()
        target = (root / relative_path).resolve()
        if root not in target.parents or not target.is_file():
            raise HTTPException(404)
        unavailable = incomplete_media_files()
        if target in unavailable:
            raise HTTPException(409, "视频仍在下载，完成后即可播放")
        media_id = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:24]
        siblings = []
        for group in scan_library(root, unavailable=unavailable):
            if group.title == Path(relative_path).parts[0]:
                siblings = group.episodes
                break
        return templates.TemplateResponse(
            request,
            "watch.html",
            context(request, file=target, relative=relative_path, media_id=media_id, siblings=siblings),
        )

    @app.get("/settings", response_class=HTMLResponse)
    async def settings(request: Request):
        root = download_root()
        usage = shutil.disk_usage(root if root.exists() else root.parent)
        return templates.TemplateResponse(
            request,
            "settings.html",
            context(
                request,
                download_dir=root,
                data_dir=data_dir,
                usage=usage,
                max_downloads=int(store.get_setting("max_downloads", "3") or 3),
                download_limit_kbps=int(store.get_setting("download_limit_kbps", "0") or 0),
                upload_limit_kbps=int(store.get_setting("upload_limit_kbps", "0") or 0),
                min_free_gb=float(store.get_setting("min_free_gb", "2") or 2),
                hidden_media=store.list_hidden_media(),
            ),
        )

    @app.post("/settings/hidden/restore")
    async def restore_hidden_media(relative_path: str = Form(...)):
        try:
            target = resolve_media_path(download_root(), relative_path)
        except ValueError:
            raise HTTPException(404) from None
        normalized = target.relative_to(download_root().resolve()).as_posix()
        store.restore_media(normalized)
        return RedirectResponse("/settings?restored=1", status_code=303)

    @app.post("/settings")
    async def update_settings(
        download_dir: str = Form(...), max_downloads: int = Form(3),
        download_limit_kbps: int = Form(0), upload_limit_kbps: int = Form(0),
        min_free_gb: float = Form(2),
    ):
        try:
            root = validate_download_directory(download_dir)
        except ValueError as exc:
            return RedirectResponse(f"/settings?error={str(exc)}", status_code=303)
        store.set_setting("download_dir", str(root))
        store.set_setting("max_downloads", str(max(1, max_downloads)))
        store.set_setting("download_limit_kbps", str(max(0, download_limit_kbps)))
        store.set_setting("upload_limit_kbps", str(max(0, upload_limit_kbps)))
        store.set_setting("min_free_gb", str(max(0.0, min_free_gb)))
        bt.configure(max(1, max_downloads), max(0, download_limit_kbps), max(0, upload_limit_kbps))
        return RedirectResponse("/settings?saved=1", status_code=303)

    @app.get("/api/danmaku/v3/")
    async def get_danmaku(id: str):
        data = [[item.time, item.type, item.color, item.author, item.text] for item in store.list_danmaku(id)]
        return {"code": 0, "data": data}

    @app.post("/api/danmaku/v3/")
    async def post_danmaku(payload: DanmakuPayload):
        text = payload.text.strip()[:100]
        if not text:
            raise HTTPException(400, "弹幕不能为空")
        store.add_danmaku(payload.id, max(0, payload.time), payload.type, payload.color, payload.author[:30], text)
        return {"code": 0, "data": {}}

    @app.get("/api/progress/{media_id}")
    async def get_progress(media_id: str):
        item = store.get_progress(media_id)
        return {"position": item.position if item else 0, "duration": item.duration if item else 0}

    @app.post("/api/progress/{media_id}")
    async def save_progress(media_id: str, payload: ProgressPayload):
        store.save_progress(media_id, max(0, payload.position), max(0, payload.duration))
        return {"ok": True}

    return app


def _title_matches(title: str, normalized_release: str) -> bool:
    words = [word for word in title.casefold().replace("第三季", "").split() if len(word) > 1]
    compact_title = title.casefold().replace(" ", "")
    return compact_title in normalized_release or any(word in normalized_release for word in words)


def _safe_name(value: str) -> str:
    return "".join(char if char not in '<>:"/\\|?*' else "_" for char in value).strip()[:120]


def _media_files(root: Path) -> list[dict[str, str]]:
    if not root.exists():
        return []
    extensions = {".mp4", ".mkv", ".webm", ".avi"}
    return [
        {"name": path.name, "relative": path.relative_to(root).as_posix(), "ext": path.suffix.lower()}
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in extensions
    ]


app = create_app()
