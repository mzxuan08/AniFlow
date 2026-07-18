from __future__ import annotations

import re
from dataclasses import dataclass

from .matching import classify_release, extract_episode


@dataclass(frozen=True, slots=True)
class EpisodeOverview:
    latest_released: int | None
    released: set[int]
    downloaded: set[int]
    active: set[int]
    missing: set[int]


def build_episode_overview(
    subscription_title: str,
    release_titles: list[str],
    task_titles: list[str],
    media_names: list[str],
) -> EpisodeOverview:
    released = {
        episode
        for title in release_titles
        if _title_matches(subscription_title, title)
        and classify_release(title).accepted
        for _season, episode in [extract_episode(title)]
        if episode is not None
    }
    downloaded = {
        episode
        for name in media_names
        for _season, episode in [extract_episode(name)]
        if episode is not None
    }
    active = {
        episode
        for title in task_titles
        if _title_matches(subscription_title, title)
        for _season, episode in [extract_episode(title)]
        if episode is not None
    }
    return EpisodeOverview(
        latest_released=max(released) if released else None,
        released=released,
        downloaded=downloaded,
        active=active,
        missing=released - downloaded - active,
    )


def _title_matches(subscription_title: str, candidate: str) -> bool:
    needle = re.sub(r"[\W_]+", "", subscription_title.casefold())
    haystack = re.sub(r"[\W_]+", "", candidate.casefold())
    return bool(needle and needle in haystack)
