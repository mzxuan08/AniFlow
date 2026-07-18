from __future__ import annotations

import re
from datetime import datetime, timedelta

from .matching import classify_release, extract_episode, release_version
from .mikan import Release


def health_snapshot(
    previous_progress: float,
    progress: float,
    peer_count: int,
    seed_count: int,
    now: datetime,
) -> dict[str, object]:
    changed = progress > previous_progress + 0.01
    values: dict[str, object] = {
        "peer_count": max(0, peer_count),
        "seed_count": max(0, seed_count),
        "status": "健康" if changed else "连接中",
    }
    if changed:
        values["last_progress"] = progress
        values["last_progress_at"] = now
    return values


def assess_health(
    task_state: str,
    last_progress_at: datetime,
    now: datetime,
    stall_minutes: int,
) -> str:
    if task_state == "暂停":
        return "暂停"
    if task_state not in {"等待中", "下载中"}:
        return task_state
    if now - last_progress_at >= timedelta(minutes=max(1, stall_minutes)):
        return "停滞"
    return "连接中"


def choose_replacement(
    releases: list[Release],
    subscription_title: str,
    season: int | None,
    episode: int,
    attempted_guids: set[str],
) -> Release | None:
    normalized_title = _normalize(subscription_title)
    candidates: list[tuple[int, int, Release]] = []
    for release in releases:
        if release.guid in attempted_guids or "1080p" not in release.title.casefold():
            continue
        release_season, release_episode = extract_episode(release.title)
        if release_episode != episode or release_season != season:
            continue
        if normalized_title not in _normalize(release.title):
            continue
        match = classify_release(release.title)
        if match.accepted:
            candidates.append((release_version(release.title), match.score, release))
    return max(candidates, key=lambda item: (item[0], item[1]))[2] if candidates else None


def _normalize(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.casefold())
