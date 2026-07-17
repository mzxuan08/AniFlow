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
