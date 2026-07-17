from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .matching import extract_episode


@dataclass(frozen=True, slots=True)
class MediaEpisode:
    name: str
    relative: str
    episode: int | None
    size: int
    ext: str


@dataclass(frozen=True, slots=True)
class MediaGroup:
    title: str
    episodes: list[MediaEpisode]


LibraryScanner = Callable[
    [Path, set[str] | None, set[Path] | None],
    list[MediaGroup],
]


class MediaLibraryCache:
    def __init__(self, scanner: LibraryScanner, ttl_seconds: float = 15) -> None:
        self.scanner = scanner
        self.ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()
        self._key: tuple[Path, frozenset[str], frozenset[Path]] | None = None
        self._value: list[MediaGroup] = []
        self._expires_at = 0.0

    async def get(
        self,
        root: Path,
        hidden: set[str] | None = None,
        unavailable: set[Path] | None = None,
        *,
        force: bool = False,
    ) -> list[MediaGroup]:
        normalized_hidden = frozenset(hidden or set())
        normalized_unavailable = frozenset(
            path.resolve() for path in (unavailable or set())
        )
        key = (root.resolve(), normalized_hidden, normalized_unavailable)
        now = time.monotonic()
        if not force and key == self._key and now < self._expires_at:
            return self._value
        async with self._lock:
            now = time.monotonic()
            if not force and key == self._key and now < self._expires_at:
                return self._value
            value = await asyncio.to_thread(
                self.scanner,
                key[0],
                set(normalized_hidden),
                set(normalized_unavailable),
            )
            self._key = key
            self._value = value
            self._expires_at = time.monotonic() + self.ttl_seconds
            return value

    def invalidate(self) -> None:
        self._key = None
        self._value = []
        self._expires_at = 0.0


def resolve_media_path(root: Path, relative_path: str) -> Path:
    resolved_root = root.resolve()
    target = (resolved_root / relative_path).resolve()
    if target == resolved_root or resolved_root not in target.parents:
        raise ValueError("媒体路径超出下载目录")
    return target


def scan_library(
    root: Path,
    hidden: set[str] | None = None,
    unavailable: set[Path] | None = None,
) -> list[MediaGroup]:
    if not root.exists():
        return []
    hidden = hidden or set()
    unavailable = {path.resolve() for path in (unavailable or set())}
    extensions = {".mp4", ".mkv", ".webm", ".avi"}
    grouped: dict[str, list[MediaEpisode]] = {}
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        if path.resolve() in unavailable:
            continue
        relative = path.relative_to(root)
        if relative.as_posix() in hidden:
            continue
        title = relative.parts[0] if len(relative.parts) > 1 else "未分类"
        _season, episode = extract_episode(path.name)
        grouped.setdefault(title, []).append(
            MediaEpisode(path.name, relative.as_posix(), episode, path.stat().st_size, path.suffix.lower())
        )
    return [
        MediaGroup(title, sorted(items, key=lambda item: item.episode or -1, reverse=True))
        for title, items in sorted(grouped.items())
    ]
