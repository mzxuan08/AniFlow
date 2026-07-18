from fastapi.testclient import TestClient
import pytest
from pathlib import Path
from datetime import datetime, timedelta

from aniflow.app import create_app
from aniflow.mikan import Bangumi, Release


class FakeMikan:
    def __init__(self):
        self.catalog_calls = 0

    async def catalog(self):
        self.catalog_calls += 1
        return []

    async def rss(self):
        return []

    async def torrent(self, _url):
        return b"torrent-bytes"

    async def bangumi_releases(self, _source_id):
        return []


class RecordingEngine:
    available = True
    error = None

    def __init__(self):
        self.added = []
        self.actions = []

    def add_torrent(self, task_id, torrent_data, save_path):
        self.added.append((task_id, torrent_data, save_path))

    def pause(self, task_id):
        self.actions.append(("pause", task_id))

    def resume(self, task_id):
        self.actions.append(("resume", task_id))

    def remove(self, task_id, delete_files=False):
        self.actions.append(("remove", task_id, delete_files))

    def restore(self, task_id, save_path):
        self.actions.append(("restore", task_id, save_path))

    def configure(self, max_downloads, download_limit_kbps, upload_limit_kbps):
        self.actions.append(("configure", max_downloads, download_limit_kbps, upload_limit_kbps))


def test_dashboard_is_public_and_has_navigation(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())

    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "AniFlow" in response.text
    assert "番剧发现" in response.text
    assert "登录" not in response.text


def test_shell_has_local_theme_toggle_and_mobile_navigation(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())

    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert 'id="theme-toggle"' in response.text
    assert 'id="theme-toggle-mobile"' in response.text
    assert 'class="mobile-nav"' in response.text
    assert '/static/app.js' in response.text
    assert 'data-theme' in response.text


def test_static_assets_are_compressed_and_cached(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())

    response = TestClient(app).get(
        "/static/DPlayer.min.js", headers={"Accept-Encoding": "gzip"}
    )

    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert response.headers["cache-control"] == "public, max-age=3600"


def test_dashboard_uses_comfort_ui_sections(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())

    response = TestClient(app).get("/")

    assert 'class="hero-card"' in response.text
    assert 'class="metric-grid"' in response.text
    assert "订阅状态" in response.text


def test_subscribe_from_public_dashboard(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    client = TestClient(app)

    response = client.post(
        "/subscriptions",
        data={"source_id": "4014", "title": "碧蓝之海 第三季", "poster_url": ""},
        follow_redirects=False,
    )

    assert response.status_code == 303
    page = client.get("/subscriptions")
    assert "碧蓝之海 第三季" in page.text


def test_subscribe_downloads_latest_best_1080p_release(tmp_path):
    class BackfillMikan(FakeMikan):
        async def bangumi_releases(self, _source_id):
            return [
                Release("1", "Anime - 13 [简体][1080P][MP4]", "https://x/1", "https://x/e1"),
                Release("2", "Anime - 14 [简体][1080P][MP4]", "https://x/2", "https://x/e2"),
            ]

    engine = RecordingEngine()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}",
        mikan_client=BackfillMikan(),
        engine=engine,
    )

    response = TestClient(app).post(
        "/subscriptions",
        data={"source_id": "3952", "title": "史莱姆第四季", "poster_url": ""},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert len(engine.added) == 1
    assert app.state.store.list_tasks()[0].title.startswith("Anime - 14")


def test_subscription_page_can_check_and_download_now(tmp_path):
    class BackfillMikan(FakeMikan):
        async def bangumi_releases(self, _source_id):
            return [
                Release("latest", "Anime - 14 [简体内嵌][1080P][MP4]", "https://x/latest", "https://x/e")
            ]

    engine = RecordingEngine()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}",
        mikan_client=BackfillMikan(),
        engine=engine,
    )
    app.state.store.subscribe("3952", "史莱姆第四季", None)
    client = TestClient(app)

    page = client.get("/subscriptions")
    first = client.post("/subscriptions/3952/refresh", follow_redirects=False)
    second = client.post("/subscriptions/3952/refresh", follow_redirects=False)

    assert "立即检查并下载" in page.text
    assert first.status_code == 303
    assert "result=started" in first.headers["location"]
    assert "result=exists" in second.headers["location"]
    assert len(engine.added) == 1


def test_tasks_page_has_manual_status_refresh(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())

    response = TestClient(app).get("/tasks")

    assert response.status_code == 200
    assert "刷新任务状态" in response.text
    assert 'href="/tasks"' in response.text


def test_tasks_and_library_use_media_center_layout(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    client = TestClient(app)

    tasks = client.get("/tasks")
    library = client.get("/library")

    assert 'class="queue-overview"' in tasks.text
    assert "下载队列" in tasks.text
    assert 'class="library-hero"' in library.text
    assert "媒体库" in library.text


def test_library_page_caches_scan_and_supports_forced_refresh(tmp_path):
    calls = []

    def scanner(root, hidden=None, unavailable=None):
        calls.append((root, hidden, unavailable))
        return []

    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}",
        mikan_client=FakeMikan(),
        library_scanner=scanner,
    )
    client = TestClient(app)

    first = client.get("/library")
    client.get("/library")
    client.get("/library?refresh=1")

    assert len(calls) == 2
    assert "刷新媒体库" in first.text


def test_library_hides_incomplete_torrent_files_and_blocks_direct_playback(tmp_path):
    class IncompleteEngine(RecordingEngine):
        def __init__(self, incomplete):
            super().__init__()
            self.incomplete = incomplete

        def incomplete_files(self):
            return self.incomplete

    media_root = tmp_path / "media"
    episode = media_root / "Anime" / "Anime - 01 [1080P].mp4"
    episode.parent.mkdir(parents=True)
    episode.write_bytes(b"partial-video")
    engine = IncompleteEngine({episode.resolve()})
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}",
        mikan_client=FakeMikan(),
        engine=engine,
    )
    app.state.store.set_setting("download_dir", str(media_root))
    client = TestClient(app)

    assert "Anime - 01" not in client.get("/library").text
    assert client.get("/watch/Anime/Anime%20-%2001%20%5B1080P%5D.mp4").status_code == 409
    assert client.get("/media/Anime/Anime%20-%2001%20%5B1080P%5D.mp4").status_code == 409


def test_watch_page_uses_dplayer_danmaku_api_root(tmp_path):
    media_root = tmp_path / "media"
    episode = media_root / "Anime" / "Anime - 01 [1080P].mp4"
    episode.parent.mkdir(parents=True)
    episode.write_bytes(b"video")
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    app.state.store.set_setting("download_dir", str(media_root))

    response = TestClient(app).get("/watch/Anime/Anime%20-%2001%20%5B1080P%5D.mp4")

    assert response.status_code == 200
    assert "api:'/api/danmaku/'" in response.text
    assert "/api/danmaku/v3/v3/" not in response.text


def test_library_can_hide_episode_without_deleting_local_file(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    media_root = tmp_path / "media"
    episode = media_root / "Anime" / "Anime - 01 [1080P].mp4"
    episode.parent.mkdir(parents=True)
    episode.write_bytes(b"video")
    app.state.store.set_setting("download_dir", str(media_root))
    client = TestClient(app)

    page = client.get("/library")
    response = client.post(
        "/library/remove",
        data={"relative_path": "Anime/Anime - 01 [1080P].mp4"},
        follow_redirects=False,
    )

    assert "仅从媒体库移除" in page.text
    assert "同时删除本地文件" in page.text
    assert response.status_code == 303
    assert episode.is_file()
    assert app.state.store.list_hidden_media() == ["Anime/Anime - 01 [1080P].mp4"]
    assert "Anime - 01" not in client.get("/library").text


def test_library_can_delete_episode_file_and_empty_directory(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    media_root = tmp_path / "media"
    episode = media_root / "Anime" / "Anime - 01 [1080P].mp4"
    episode.parent.mkdir(parents=True)
    episode.write_bytes(b"video")
    app.state.store.set_setting("download_dir", str(media_root))

    response = TestClient(app).post(
        "/library/remove",
        data={
            "relative_path": "Anime/Anime - 01 [1080P].mp4",
            "delete_file": "true",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert not episode.exists()
    assert not episode.parent.exists()
    assert app.state.store.list_hidden_media() == []


def test_settings_can_restore_hidden_media(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    media_root = tmp_path / "media"
    episode = media_root / "Anime" / "Anime - 01 [1080P].mp4"
    episode.parent.mkdir(parents=True)
    episode.write_bytes(b"video")
    app.state.store.set_setting("download_dir", str(media_root))
    app.state.store.hide_media("Anime/Anime - 01 [1080P].mp4")
    client = TestClient(app)

    settings = client.get("/settings")
    response = client.post(
        "/settings/hidden/restore",
        data={"relative_path": "Anime/Anime - 01 [1080P].mp4"},
        follow_redirects=False,
    )

    assert "已隐藏媒体" in settings.text
    assert response.status_code == 303
    assert app.state.store.list_hidden_media() == []
    assert "Anime - 01" in client.get("/library").text


def test_library_remove_rejects_path_outside_download_root(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    media_root = tmp_path / "media"
    media_root.mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"keep")
    app.state.store.set_setting("download_dir", str(media_root))

    response = TestClient(app).post(
        "/library/remove",
        data={"relative_path": "../outside.mp4", "delete_file": "true"},
        follow_redirects=False,
    )

    assert response.status_code == 404
    assert outside.read_bytes() == b"keep"


def test_library_delete_reports_permission_error_without_hiding_file(tmp_path, monkeypatch):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    media_root = tmp_path / "media"
    episode = media_root / "Anime" / "Anime - 01 [1080P].mp4"
    episode.parent.mkdir(parents=True)
    episode.write_bytes(b"video")
    app.state.store.set_setting("download_dir", str(media_root))

    def deny_delete(_path):
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "unlink", deny_delete)
    response = TestClient(app).post(
        "/library/remove",
        data={
            "relative_path": "Anime/Anime - 01 [1080P].mp4",
            "delete_file": "true",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "result=permission_error" in response.headers["location"]
    assert episode.is_file()
    assert app.state.store.list_hidden_media() == []


def test_settings_updates_global_download_directory(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    target = tmp_path / "media"

    response = TestClient(app).post(
        "/settings", data={"download_dir": str(target)}, follow_redirects=False
    )

    assert response.status_code == 303
    assert app.state.store.get_setting("download_dir") == str(target.resolve())


def test_settings_updates_local_staging_directory(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    library = tmp_path / "library"
    staging = tmp_path / "staging"

    response = TestClient(app).post(
        "/settings",
        data={"download_dir": str(library), "staging_dir": str(staging)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert app.state.store.get_setting("download_dir") == str(library.resolve())
    assert app.state.store.get_setting("staging_dir") == str(staging.resolve())


def test_settings_apply_limits_to_engine(tmp_path):
    engine = RecordingEngine()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan(), engine=engine
    )

    response = TestClient(app).post(
        "/settings",
        data={
            "download_dir": str(tmp_path / "media"),
            "max_downloads": "3",
            "download_limit_kbps": "2048",
            "upload_limit_kbps": "512",
            "min_free_gb": "5",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert ("configure", 3, 2048, 512) in engine.actions
    assert app.state.store.get_setting("min_free_gb") == "5.0"


def test_settings_page_shows_download_controls(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())

    response = TestClient(app).get("/settings")

    assert response.status_code == 200
    assert 'name="max_downloads"' in response.text
    assert 'name="download_limit_kbps"' in response.text
    assert 'name="upload_limit_kbps"' in response.text
    assert 'name="min_free_gb"' in response.text
    assert 'name="staging_dir"' in response.text
    assert "临时下载目录" in response.text


def test_archiving_task_shows_safe_controls(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    task = app.state.store.create_task(
        "Anime - 01",
        str(tmp_path / "library"),
        working_path=str(tmp_path / "staging"),
    )
    app.state.store.update_task(task.id, state="整理失败", error="disk error")

    response = TestClient(app).get("/tasks")

    assert "重试归档" in response.text
    assert f'/tasks/{task.id}/pause' not in response.text


def test_subscription_does_not_start_when_disk_reserve_is_reached(tmp_path, monkeypatch):
    class BackfillMikan(FakeMikan):
        async def bangumi_releases(self, _source_id):
            return [
                Release("latest", "Anime - 14 [简体][1080P][MP4]", "https://x/latest", "https://x/e")
            ]

    engine = RecordingEngine()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}",
        mikan_client=BackfillMikan(),
        engine=engine,
    )
    app.state.store.set_setting("download_dir", str(tmp_path / "media"))
    app.state.store.set_setting("min_free_gb", "5")
    monkeypatch.setattr("aniflow.app.has_minimum_free_space", lambda _root, _minimum: False)

    response = TestClient(app).post(
        "/subscriptions",
        data={"source_id": "3952", "title": "史莱姆第四季", "poster_url": ""},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "result=no_space" in response.headers["location"]
    assert engine.added == []
    assert app.state.store.list_tasks() == []


def test_task_controls_call_download_engine(tmp_path):
    engine = RecordingEngine()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan(), engine=engine
    )
    task = app.state.store.create_task("Anime - 01", str(tmp_path / "media"))
    client = TestClient(app)

    assert client.post(f"/tasks/{task.id}/pause", follow_redirects=False).status_code == 303
    assert client.post(f"/tasks/{task.id}/resume", follow_redirects=False).status_code == 303
    assert client.post(
        f"/tasks/{task.id}/delete", data={"delete_files": "true"}, follow_redirects=False
    ).status_code == 303
    assert engine.actions == [("pause", task.id), ("resume", task.id), ("remove", task.id, True)]


def test_deleting_completed_files_restores_engine_handle_first(tmp_path):
    class RestoreRequiredEngine(RecordingEngine):
        def __init__(self):
            super().__init__()
            self.restored = set()

        def restore(self, task_id, save_path):
            self.restored.add(task_id)
            self.actions.append(("restore", task_id, save_path))

        def remove(self, task_id, delete_files=False):
            if task_id not in self.restored:
                raise KeyError(task_id)
            self.actions.append(("remove", task_id, delete_files))

    engine = RestoreRequiredEngine()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan(), engine=engine
    )
    task = app.state.store.create_task("Anime - 01", str(tmp_path / "media"))
    app.state.store.update_task(task.id, state="已完成", progress=100)

    response = TestClient(app).post(
        f"/tasks/{task.id}/delete", data={"delete_files": "true"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert engine.actions == [
        ("restore", task.id, Path(task.save_path)),
        ("remove", task.id, True),
    ]


def test_startup_restores_unfinished_tasks(tmp_path):
    engine = RecordingEngine()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan(), engine=engine
    )
    task = app.state.store.create_task("Anime - 01", str(tmp_path / "media"))

    with TestClient(app):
        pass

    assert ("restore", task.id, Path(task.save_path)) in engine.actions


def test_startup_restores_saved_engine_limits(tmp_path):
    engine = RecordingEngine()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan(), engine=engine
    )
    app.state.store.set_setting("max_downloads", "4")
    app.state.store.set_setting("download_limit_kbps", "3072")
    app.state.store.set_setting("upload_limit_kbps", "256")

    with TestClient(app):
        pass

    assert ("configure", 4, 3072, 256) in engine.actions


@pytest.mark.asyncio
async def test_refresh_submits_matching_release_to_download_engine(tmp_path):
    class ReleasingMikan(FakeMikan):
        async def rss(self):
            return [
                Release(
                    "guid-1",
                    "[Group] 碧蓝之海 第三季 - 02 [简中][内嵌][1080P][MP4]",
                    "https://example/1.torrent",
                    "https://example/episode/1",
                )
            ]

    engine = RecordingEngine()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}",
        mikan_client=ReleasingMikan(),
        engine=engine,
    )
    app.state.store.subscribe("4014", "碧蓝之海 第三季", None)

    created = await app.state.refresh_releases()

    assert created == 1
    assert engine.added[0][1] == b"torrent-bytes"
    assert app.state.store.list_tasks()[0].state == "等待中"


@pytest.mark.asyncio
async def test_new_download_uses_local_staging_before_media_library(tmp_path):
    class ReleasingMikan(FakeMikan):
        async def rss(self):
            return [
                Release(
                    "guid-staged",
                    "[Group] Anime - 01 [简中][内嵌][1080P][MP4]",
                    "https://example/1.torrent",
                    "https://example/episode/1",
                )
            ]

    engine = RecordingEngine()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}",
        mikan_client=ReleasingMikan(),
        engine=engine,
    )
    library_root = tmp_path / "library"
    staging_root = tmp_path / "staging"
    app.state.store.set_setting("download_dir", str(library_root))
    app.state.store.set_setting("staging_dir", str(staging_root))
    app.state.store.subscribe("1", "Anime", None)

    created = await app.state.refresh_releases()

    task = app.state.store.list_tasks()[0]
    assert created == 1
    assert Path(task.save_path) == library_root / "Anime"
    assert Path(task.working_path) == staging_root / "Anime"
    assert engine.added[0][2] == staging_root / "Anime"


@pytest.mark.asyncio
async def test_completed_staged_task_moves_files_to_media_library(tmp_path):
    class ArchivingEngine(RecordingEngine):
        def __init__(self, files):
            super().__init__()
            self.files = files

        def torrent_files(self, _task_id, _root):
            return self.files

        def detach(self, task_id):
            self.actions.append(("detach", task_id))

    staging = tmp_path / "staging" / "Anime"
    library = tmp_path / "library" / "Anime"
    episode = staging / "Anime - 01.mp4"
    episode.parent.mkdir(parents=True)
    episode.write_bytes(b"video")
    engine = ArchivingEngine([episode])
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}",
        mikan_client=FakeMikan(),
        engine=engine,
    )
    task = app.state.store.create_task(
        "Anime - 01", str(library), working_path=str(staging)
    )
    app.state.store.update_task(task.id, state="已完成", progress=100)

    archived = await app.state.finalize_downloads()

    updated = app.state.store.list_tasks()[0]
    assert archived == 1
    assert (library / "Anime - 01.mp4").read_bytes() == b"video"
    assert updated.working_path is None
    assert updated.state == "已完成"
    assert ("detach", task.id) in engine.actions
    assert app.state.store.unread_notification_count() == 1


@pytest.mark.asyncio
async def test_failed_archive_preserves_files_and_can_be_retried(tmp_path):
    class ArchivingEngine(RecordingEngine):
        def __init__(self, files):
            super().__init__()
            self.files = files

        def torrent_files(self, _task_id, _root):
            return self.files

        def detach(self, task_id):
            self.actions.append(("detach", task_id))

    staging = tmp_path / "staging" / "Anime"
    library = tmp_path / "library" / "Anime"
    staging.mkdir(parents=True)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"keep")
    engine = ArchivingEngine([outside])
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}",
        mikan_client=FakeMikan(),
        engine=engine,
    )
    task = app.state.store.create_task(
        "Anime - 01", str(library), working_path=str(staging)
    )
    app.state.store.update_task(task.id, state="已完成", progress=100)

    archived = await app.state.finalize_downloads()

    failed = app.state.store.list_tasks()[0]
    assert archived == 0
    assert failed.state == "整理失败"
    assert outside.read_bytes() == b"keep"

    episode = staging / "Anime - 01.mp4"
    episode.write_bytes(b"video")
    engine.files = [episode]
    app.state.store.update_task(task.id, state="整理中", error=None)

    retried = await app.state.finalize_downloads()

    completed = app.state.store.list_tasks()[0]
    assert retried == 1
    assert completed.state == "已完成"
    assert completed.working_path is None
    assert (library / "Anime - 01.mp4").read_bytes() == b"video"


@pytest.mark.asyncio
async def test_refresh_only_downloads_v2_when_same_episode_has_two_versions(tmp_path):
    class VersionedMikan(FakeMikan):
        async def rss(self):
            return [
                Release("v1", "[云光字幕组] 二十世纪电气目录 [01][简体双语][1080p]", "https://x/v1", "https://x/e1"),
                Release("v2", "[樱桃花字幕组] 二十世纪电气目录 - 1 v2 [1080p][简日内嵌]", "https://x/v2", "https://x/e2"),
            ]

    engine = RecordingEngine()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}",
        mikan_client=VersionedMikan(),
        engine=engine,
    )
    app.state.store.subscribe("4050", "二十世纪电气目录", None)

    created = await app.state.refresh_releases()

    assert created == 1
    assert len(engine.added) == 1
    assert "v2" in app.state.store.list_tasks()[0].title.casefold()


@pytest.mark.asyncio
async def test_later_v2_replaces_unfinished_same_episode_task_and_files(tmp_path):
    class V2Mikan(FakeMikan):
        async def rss(self):
            return [
                Release("v2", "[樱桃花字幕组] 二十世纪电气目录 - 1 v2 [1080p][简日内嵌]", "https://x/v2", "https://x/e2")
            ]

    engine = RecordingEngine()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=V2Mikan(), engine=engine
    )
    app.state.store.set_setting("download_dir", str(tmp_path / "media"))
    app.state.store.subscribe("4050", "二十世纪电气目录", None)
    old = app.state.store.create_task(
        "[云光字幕组] 二十世纪电气目录 [01][简体双语][1080p]",
        str(tmp_path / "media" / "二十世纪电气目录"),
    )

    created = await app.state.refresh_releases()

    assert created == 1
    assert ("remove", old.id, True) in engine.actions
    tasks = app.state.store.list_tasks()
    assert len(tasks) == 1
    assert "v2" in tasks[0].title.casefold()


@pytest.mark.asyncio
async def test_automatic_refresh_skips_new_tasks_when_disk_reserve_is_reached(
    tmp_path, monkeypatch
):
    class ReleasingMikan(FakeMikan):
        async def rss(self):
            return [
                Release(
                    "guid-low-space",
                    "[字幕组] 碧蓝之海 第三季 - 02 [简中][内嵌][1080P]",
                    "https://example/low-space.torrent",
                    "https://example/episode/2",
                )
            ]

    engine = RecordingEngine()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}",
        mikan_client=ReleasingMikan(),
        engine=engine,
    )
    app.state.store.subscribe("4014", "碧蓝之海 第三季", None)
    monkeypatch.setattr("aniflow.app.has_minimum_free_space", lambda _root, _minimum: False)

    created = await app.state.refresh_releases()

    assert created == 0
    assert engine.added == []
    assert app.state.store.list_tasks() == []


def test_manual_download_reports_low_disk_space(tmp_path, monkeypatch):
    engine = RecordingEngine()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan(), engine=engine
    )
    monkeypatch.setattr("aniflow.app.has_minimum_free_space", lambda _root, _minimum: False)

    response = TestClient(app).post(
        "/tasks/manual",
        data={"title": "Anime - 01 [简体][1080P]", "torrent_url": "https://x/1.torrent"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "error=no_space" in response.headers["location"]
    assert engine.added == []
    assert app.state.store.list_tasks() == []


def test_discover_uses_cached_catalog_without_remote_request(tmp_path):
    mikan = FakeMikan()
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=mikan)
    app.state.store.replace_catalog(
        [Bangumi("4014", "碧蓝之海 第三季", "https://mikan/4014", None)]
    )

    response = TestClient(app).get("/discover?q=碧蓝")

    assert response.status_code == 200
    assert "碧蓝之海 第三季" in response.text
    assert mikan.catalog_calls == 0


def test_discover_uses_local_poster_endpoint_instead_of_remote_image(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    app.state.store.replace_catalog(
        [Bangumi("4014", "碧蓝之海 第三季", "https://mikan/4014", "https://mikanani.me/remote.jpg")]
    )

    response = TestClient(app).get("/discover")

    assert 'src="/posters/4014"' in response.text
    assert "https://mikanani.me/remote.jpg" not in response.text


def test_missing_local_poster_returns_fast_placeholder(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())

    response = TestClient(app).get("/posters/4014")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")


def test_manual_catalog_refresh_updates_cache(tmp_path):
    class CatalogMikan(FakeMikan):
        async def catalog(self):
            self.catalog_calls += 1
            return [Bangumi("4014", "碧蓝之海 第三季", "https://mikan/4014", None)]

    mikan = CatalogMikan()
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=mikan)
    client = TestClient(app)

    response = client.post("/discover/refresh", follow_redirects=False)

    assert response.status_code == 303
    assert mikan.catalog_calls == 1
    assert app.state.store.list_catalog()[0].title == "碧蓝之海 第三季"


@pytest.mark.asyncio
async def test_stalled_task_switches_to_untried_same_episode_candidate(tmp_path):
    class ReplacementMikan(FakeMikan):
        async def rss(self):
            return [
                Release("v1", "[Group] Anime - 02 [1080p][简体][内嵌]", "https://x/v1", "https://x/1"),
                Release("v2", "[Group] Anime - 02 v2 [1080p][简体][内嵌]", "https://x/v2", "https://x/2"),
            ]

        async def torrent(self, url):
            return f"torrent:{url}".encode()

    engine = RecordingEngine()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}",
        mikan_client=ReplacementMikan(),
        engine=engine,
    )
    app.state.store.subscribe("4014", "Anime", None)
    release, _ = app.state.store.record_release("v1", "Anime - 02", "https://x/v1")
    task = app.state.store.create_task("Anime - 02", str(tmp_path / "Anime"), release.id)
    app.state.store.update_task(task.id, state="下载中", progress=10)
    app.state.store.update_task_health(
        task.id,
        source_id="4014",
        season=None,
        episode=2,
        last_progress=10,
        last_progress_at=datetime.utcnow() - timedelta(minutes=31),
        attempted_guids=["v1"],
    )

    switched = await app.state.check_download_health()

    updated = app.state.store.list_tasks()[0]
    health = app.state.store.get_task_health(task.id)
    assert switched == 1
    assert ("remove", task.id, True) in engine.actions
    assert engine.added[-1] == (task.id, b"torrent:https://x/v2", Path(task.save_path))
    assert "v2" in updated.title
    assert health is not None
    assert health.switch_count == 1
    assert health.attempted_guid_list == ["v1", "v2"]
    assert app.state.store.unread_notification_count() == 1


@pytest.mark.asyncio
async def test_stalled_task_without_candidate_notifies_only_once(tmp_path):
    class NoReplacementMikan(FakeMikan):
        async def rss(self):
            return [
                Release("v1", "[Group] Anime - 02 [1080p][简体][内嵌]", "https://x/v1", "https://x/1")
            ]

    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}",
        mikan_client=NoReplacementMikan(),
        engine=RecordingEngine(),
    )
    app.state.store.subscribe("4014", "Anime", None)
    task = app.state.store.create_task("Anime - 02", str(tmp_path / "Anime"))
    app.state.store.update_task(task.id, state="下载中")
    app.state.store.update_task_health(
        task.id,
        source_id="4014",
        episode=2,
        last_progress_at=datetime.utcnow() - timedelta(minutes=31),
        attempted_guids=["v1"],
    )

    assert await app.state.check_download_health() == 0
    assert await app.state.check_download_health() == 0

    health = app.state.store.get_task_health(task.id)
    assert health is not None
    assert health.status == "需处理"
    assert app.state.store.unread_notification_count() == 1


def test_notification_center_shows_unread_count_marks_read_and_clears(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    app.state.store.add_notification("下载完成", "Anime - 01", "已归档", "/library")
    app.state.store.add_notification("缺集发现", "Anime", "缺少第 2 集", "/subscriptions")
    client = TestClient(app)

    dashboard = client.get("/")
    notifications = client.get("/notifications")

    assert 'class="notification-count">2<' in dashboard.text
    assert notifications.status_code == 200
    assert "Anime - 01" in notifications.text
    assert "缺少第 2 集" in notifications.text
    assert app.state.store.unread_notification_count() == 0

    cleared = client.post("/notifications/clear", follow_redirects=False)
    assert cleared.status_code == 303
    assert app.state.store.list_notifications() == []


def test_unified_search_groups_catalog_subscriptions_tasks_and_media(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    app.state.store.replace_catalog(
        [Bangumi("4014", "Anime Catalog", "https://x/catalog", None)]
    )
    app.state.store.subscribe("4015", "Anime Subscription", None)
    app.state.store.create_task("Anime Task - 01", str(tmp_path / "media"))
    media = tmp_path / "library" / "Anime Library"
    media.mkdir(parents=True)
    (media / "Anime Library - 01.mp4").write_bytes(b"video")
    app.state.store.set_setting("download_dir", str(tmp_path / "library"))

    response = TestClient(app).get("/search?q=Anime")

    assert response.status_code == 200
    assert "Anime Catalog" in response.text
    assert "Anime Subscription" in response.text
    assert "Anime Task - 01" in response.text
    assert "Anime Library" in response.text


def test_bulk_task_action_pauses_selected_tasks_only(tmp_path):
    engine = RecordingEngine()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}",
        mikan_client=FakeMikan(),
        engine=engine,
    )
    first = app.state.store.create_task("Anime - 01", str(tmp_path / "one"))
    second = app.state.store.create_task("Anime - 02", str(tmp_path / "two"))

    response = TestClient(app).post(
        "/tasks/bulk",
        data={"task_ids": str(first.id), "action": "pause"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert ("pause", first.id) in engine.actions
    assert ("pause", second.id) not in engine.actions
    states = {task.id: task.state for task in app.state.store.list_tasks()}
    assert states[first.id] == "暂停"
    assert states[second.id] == "等待中"


@pytest.mark.asyncio
async def test_missing_episode_can_be_downloaded_directly(tmp_path):
    class EpisodeMikan(FakeMikan):
        async def rss(self):
            return [
                Release("e1", "[Group] Anime - 01 [1080p][简体][内嵌]", "https://x/1", "https://x/1"),
                Release("e2", "[Group] Anime - 02 [1080p][简体][内嵌]", "https://x/2", "https://x/2"),
            ]

    engine = RecordingEngine()
    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'web.db'}",
        mikan_client=EpisodeMikan(),
        engine=engine,
    )
    app.state.store.subscribe("4014", "Anime", None)

    response = TestClient(app).post(
        "/subscriptions/4014/episodes/2/download", follow_redirects=False
    )

    assert response.status_code == 303
    assert len(engine.added) == 1
    assert "02" in app.state.store.list_tasks()[0].title
