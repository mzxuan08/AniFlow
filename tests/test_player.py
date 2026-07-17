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
