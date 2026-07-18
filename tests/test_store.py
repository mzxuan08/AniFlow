import sqlite3

from aniflow.store import Store
from aniflow.mikan import Bangumi


def test_subscription_round_trip(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'test.db'}")
    store.create_schema()

    subscription = store.subscribe("4014", "碧蓝之海 第三季", "https://example/poster.jpg")

    assert subscription.enabled is True
    assert store.list_subscriptions()[0].title == "碧蓝之海 第三季"


def test_release_guid_is_deduplicated(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'test.db'}")
    store.create_schema()

    first, created_first = store.record_release("guid-1", "Anime - 01 [简中]", "https://x/1.torrent")
    second, created_second = store.record_release("guid-1", "Anime - 01 [简中]", "https://x/1.torrent")

    assert created_first is True
    assert created_second is False
    assert first.id == second.id


def test_catalog_cache_replaces_old_items(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'test.db'}")
    store.create_schema()
    store.replace_catalog([Bangumi("1", "旧番剧", "https://mikan/1", None)])

    store.replace_catalog([Bangumi("2", "新番剧", "https://mikan/2", "https://img/2.jpg")])

    items = store.list_catalog()
    assert [(item.source_id, item.title) for item in items] == [("2", "新番剧")]
    assert store.catalog_updated_at() is not None


def test_hidden_media_can_be_added_listed_and_restored(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'test.db'}")
    store.create_schema()

    store.hide_media("Anime/Anime - 01.mp4")

    assert store.list_hidden_media() == ["Anime/Anime - 01.mp4"]
    store.restore_media("Anime/Anime - 01.mp4")
    assert store.list_hidden_media() == []


def test_sqlite_uses_wal_and_waits_for_short_write_contention(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'store.db'}")
    store.create_schema()

    with store.engine.connect() as connection:
        journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
        synchronous = connection.exec_driver_sql("PRAGMA synchronous").scalar()
        busy_timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar()

    assert journal_mode.casefold() == "wal"
    assert synchronous == 1
    assert busy_timeout >= 5000


def test_download_task_tracks_separate_working_path(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'store.db'}")
    store.create_schema()

    task = store.create_task(
        "Anime - 01",
        str(tmp_path / "library" / "Anime"),
        working_path=str(tmp_path / "staging" / "Anime"),
    )

    assert task.save_path.endswith("library\\Anime") or task.save_path.endswith("library/Anime")
    assert task.working_path is not None
    assert "staging" in task.working_path


def test_existing_database_adds_working_path_column(tmp_path):
    database = tmp_path / "old.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE download_tasks (id INTEGER PRIMARY KEY, title VARCHAR(1000), "
            "save_path VARCHAR(1000), state VARCHAR(40))"
        )

    store = Store(f"sqlite:///{database}")
    store.create_schema()

    with sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(download_tasks)")}
    assert "working_path" in columns


def test_notifications_track_unread_state_and_can_be_cleared(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'store.db'}")
    store.create_schema()

    first = store.add_notification("下载完成", "Anime - 01", "已归档", "/library")
    store.add_notification("下载失败", "Anime - 02", "无可用节点", "/tasks")

    assert first.read is False
    assert store.unread_notification_count() == 2
    assert [item.title for item in store.list_notifications()] == ["Anime - 02", "Anime - 01"]

    store.mark_notifications_read()
    assert store.unread_notification_count() == 0

    store.clear_notifications()
    assert store.list_notifications() == []


def test_task_health_round_trip_tracks_source_and_attempts(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'store.db'}")
    store.create_schema()
    task = store.create_task("Anime - 02", str(tmp_path / "Anime"))

    store.update_task_health(
        task.id,
        source_id="4014",
        season=1,
        episode=2,
        peer_count=3,
        seed_count=1,
        status="健康",
        attempted_guids=["guid-a", "guid-b"],
    )

    health = store.get_task_health(task.id)
    assert health is not None
    assert health.source_id == "4014"
    assert health.episode == 2
    assert health.peer_count == 3
    assert health.attempted_guid_list == ["guid-a", "guid-b"]


def test_media_watched_state_can_be_toggled(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'store.db'}")
    store.create_schema()

    store.set_media_watched("media-1", True)
    assert store.is_media_watched("media-1") is True

    store.set_media_watched("media-1", False)
    assert store.is_media_watched("media-1") is False
