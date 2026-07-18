from fastapi.testclient import TestClient

from aniflow.app import create_app
from test_web import FakeMikan


def test_local_danmaku_api_round_trip(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    client = TestClient(app)

    sent = client.post(
        "/api/danmaku/v3/",
        json={"id": "media-1", "author": "local", "time": 12.5, "text": "测试弹幕", "color": 16777215, "type": 0},
    )
    loaded = client.get("/api/danmaku/v3/?id=media-1")

    assert sent.json() == {"code": 0, "data": {}}
    assert loaded.json()["data"] == [[12.5, 0, 16777215, "local", "测试弹幕"]]


def test_watch_progress_round_trip(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    client = TestClient(app)

    response = client.post("/api/progress/media-1", json={"position": 88.2, "duration": 120.0})

    assert response.status_code == 200
    assert client.get("/api/progress/media-1").json()["position"] == 88.2


def test_local_danmaku_can_be_deleted_and_cleared(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    store = app.state.store
    store.add_danmaku("media-1", 3.0, 0, 16777215, "local", "first")
    store.add_danmaku("media-1", 4.0, 0, 16777215, "local", "second")
    first_id = store.list_danmaku("media-1")[0].id

    assert store.delete_danmaku(first_id, "media-1") is True
    assert [item.text for item in store.list_danmaku("media-1")] == ["second"]

    assert store.clear_danmaku("media-1") == 1
    assert store.list_danmaku("media-1") == []


def test_progress_over_ninety_percent_marks_media_watched(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    client = TestClient(app)

    response = client.post(
        "/api/progress/media-1", json={"position": 91.0, "duration": 100.0}
    )

    assert response.json() == {"ok": True, "watched": True}
    assert app.state.store.is_media_watched("media-1") is True


def test_watched_state_can_be_toggled_manually(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    client = TestClient(app)

    watched = client.post("/api/media/media-1/watched", json={"watched": True})
    unwatched = client.post("/api/media/media-1/watched", json={"watched": False})

    assert watched.status_code == 200
    assert unwatched.json() == {"ok": True, "watched": False}
    assert app.state.store.is_media_watched("media-1") is False


def test_player_prepares_eight_second_auto_next_episode(tmp_path):
    library = tmp_path / "library" / "Anime"
    library.mkdir(parents=True)
    (library / "Anime - 01.mp4").write_bytes(b"one")
    (library / "Anime - 02.mp4").write_bytes(b"two")
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    app.state.store.set_setting("download_dir", str(tmp_path / "library"))

    response = TestClient(app).get("/watch/Anime/Anime%20-%2001.mp4")

    assert response.status_code == 200
    assert 'id="next-seconds">8<' in response.text
    assert "秒后自动播放下一集" in response.text
    assert "Anime%20-%2002.mp4" in response.text or "Anime - 02.mp4" in response.text


def test_player_labels_underscore_local_absolute_episode_number(tmp_path):
    library = tmp_path / "library" / "关于我转生变成史莱姆这档事 第四季"
    library.mkdir(parents=True)
    filename = (
        "[BeanSub][Tensei Shitara Slime Datta Ken S4]"
        "[15_87][CHS][1080P][x264_AAC].mp4"
    )
    (library / filename).write_bytes(b"video")
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    app.state.store.set_setting("download_dir", str(tmp_path / "library"))

    response = TestClient(app).get(f"/watch/{library.name}/{filename}")

    assert response.status_code == 200
    assert "第 15 集" in response.text
    assert "第 ? 集" not in response.text


def test_danmaku_management_api_lists_deletes_and_clears(tmp_path):
    app = create_app(database_url=f"sqlite:///{tmp_path / 'web.db'}", mikan_client=FakeMikan())
    store = app.state.store
    store.add_danmaku("media-1", 3.0, 0, 16777215, "local", "first")
    store.add_danmaku("media-1", 4.0, 0, 16777215, "local", "second")
    client = TestClient(app)

    items = client.get("/api/danmaku/manage/media-1").json()["items"]
    deleted = client.delete(f"/api/danmaku/manage/media-1/{items[0]['id']}")
    cleared = client.delete("/api/danmaku/manage/media-1")

    assert deleted.json() == {"ok": True}
    assert cleared.json() == {"ok": True, "deleted": 1}
