from datetime import datetime, timedelta

from aniflow.download_health import assess_health, choose_replacement, health_snapshot
from aniflow.mikan import Release


def test_progress_change_resets_stall_clock_and_marks_task_healthy():
    now = datetime(2026, 7, 18, 12, 0, 0)

    values = health_snapshot(
        previous_progress=20.0,
        progress=21.5,
        peer_count=4,
        seed_count=2,
        now=now,
    )

    assert values["last_progress"] == 21.5
    assert values["last_progress_at"] == now
    assert values["status"] == "健康"


def test_active_task_is_stalled_only_after_configured_threshold():
    now = datetime(2026, 7, 18, 12, 0, 0)

    assert assess_health("下载中", now - timedelta(minutes=31), now, 30) == "停滞"
    assert assess_health("下载中", now - timedelta(minutes=29), now, 30) == "连接中"
    assert assess_health("暂停", now - timedelta(hours=2), now, 30) == "暂停"


def test_replacement_uses_untried_best_same_episode_release():
    releases = [
        Release("v1", "[Group] Anime - 02 [1080p][简体][内嵌]", "https://x/v1", "https://x/1"),
        Release("v2", "[Group] Anime - 02 v2 [1080p][简体][内嵌]", "https://x/v2", "https://x/2"),
        Release("other", "[Group] Anime - 03 [1080p][简体][内嵌]", "https://x/3", "https://x/3"),
        Release("traditional", "[Group] Anime - 02 v3 [1080p][繁体]", "https://x/v3", "https://x/4"),
    ]

    selected = choose_replacement(releases, "Anime", None, 2, {"v1"})

    assert selected is not None
    assert selected.guid == "v2"


def test_replacement_returns_none_after_all_valid_candidates_were_tried():
    releases = [
        Release("v1", "[Group] Anime - 02 [1080p][简体][内嵌]", "https://x/v1", "https://x/1")
    ]

    assert choose_replacement(releases, "Anime", None, 2, {"v1"}) is None
