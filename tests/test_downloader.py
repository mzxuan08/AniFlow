from aniflow.downloader import LibtorrentEngine


class FakeStatus:
    is_seeding = True
    progress = 1.0
    download_rate = 0


class FakeHandle:
    def status(self):
        return FakeStatus()

    def info_hash(self):
        return "hash-1"


def test_engine_does_not_publish_identical_status_twice():
    published = []
    engine = LibtorrentEngine.__new__(LibtorrentEngine)
    engine._handles = {1: FakeHandle()}
    engine._last_status = {}
    engine.on_status = lambda task_id, **values: published.append((task_id, values))

    engine._poll_once()
    engine._poll_once()

    assert len(published) == 1
    assert published[0][1]["state"] == "已完成"
