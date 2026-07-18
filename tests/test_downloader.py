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


def test_engine_publishes_peer_and_seed_health_metrics():
    class DownloadingStatus(FakeStatus):
        is_seeding = False
        progress = 0.25
        download_rate = 1024
        num_peers = 5
        num_seeds = 2

    class DownloadingHandle(FakeHandle):
        def status(self):
            return DownloadingStatus()

    published = []
    engine = LibtorrentEngine.__new__(LibtorrentEngine)
    engine._handles = {1: DownloadingHandle()}
    engine._last_status = {}
    engine.on_status = lambda *_args, **_values: None
    engine.on_health = lambda task_id, **values: published.append((task_id, values))

    engine._poll_once()

    assert published == [
        (1, {"progress": 25.0, "peer_count": 5, "seed_count": 2})
    ]
