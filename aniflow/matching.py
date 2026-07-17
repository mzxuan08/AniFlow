from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .mikan import Release


@dataclass(frozen=True, slots=True)
class ReleaseMatch:
    accepted: bool
    score: int
    subtitle_kind: str | None
    reason: str


_SIMPLIFIED = ("简中", "简体", "简繁", "简日", "chs", "gb_cn", "gb")
_TRADITIONAL = ("繁中", "繁体", "cht", "big5")
_EMBEDDED = ("内嵌", "内封", "内置")


def classify_release(title: str) -> ReleaseMatch:
    lowered = title.casefold()
    simplified = next((token for token in _SIMPLIFIED if token in lowered), None)
    traditional = next((token for token in _TRADITIONAL if token in lowered), None)

    if not simplified:
        reason = "仅检测到繁体字幕" if traditional else "未检测到简体字幕"
        return ReleaseMatch(False, 0, None, reason)

    embedded = next((token for token in _EMBEDDED if token in lowered), None)
    subtitle_kind = f"{simplified}{embedded or ''}"
    score = 60
    if simplified not in ("简繁", "简日"):
        score += 5
    if embedded:
        score += 25
    if "mp4" in lowered:
        score += 8
    if "avc" in lowered or "h264" in lowered:
        score += 5
    if "aac" in lowered:
        score += 2
    if "外挂" in lowered:
        score -= 40
    return ReleaseMatch(score >= 50, score, subtitle_kind, "符合简体字幕规则")


def extract_episode(title: str) -> tuple[int | None, int | None]:
    season_episode = re.search(r"\bS(\d{1,2})E(\d{1,3})\b", title, re.IGNORECASE)
    if season_episode:
        return int(season_episode.group(1)), int(season_episode.group(2))

    local_absolute = re.search(r"[\[(](\d{1,3})\(\d{1,3}\)[\])]", title)
    if local_absolute:
        return None, int(local_absolute.group(1))

    bracketed_episode = re.search(r"\[(\d{1,3})\]", title)
    if bracketed_episode:
        return None, int(bracketed_episode.group(1))

    separated_episode = re.search(r"\s-\s*0*(\d{1,3})(?=\s|\[|\(|\.|$)", title)
    if separated_episode:
        return None, int(separated_episode.group(1))

    plain_episode = re.search(r"(?:^|\s|-)(\d{1,3})(?:\s|\[|\(|$)", title)
    if plain_episode:
        return None, int(plain_episode.group(1))
    return None, None


def release_version(title: str) -> int:
    match = re.search(r"(?:^|[\s._-])v(\d+)(?=$|[\s._\-\[\]()])", title, re.IGNORECASE)
    return int(match.group(1)) if match else 1


def select_latest_1080p(releases: list[Release]) -> Release | None:
    candidates: list[tuple[int, int, int, Release]] = []
    for release in releases:
        if "1080p" not in release.title.casefold():
            continue
        match = classify_release(release.title)
        _season, episode = extract_episode(release.title)
        if match.accepted and episode is not None:
            candidates.append((episode, release_version(release.title), match.score, release))
    if not candidates:
        return None
    latest_episode = max(item[0] for item in candidates)
    latest = [item for item in candidates if item[0] == latest_episode]
    return max(latest, key=lambda item: (item[1], item[2]))[3]
