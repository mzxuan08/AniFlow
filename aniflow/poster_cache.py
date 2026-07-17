from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from .mikan import Bangumi

PosterFetcher = Callable[[str], Awaitable[tuple[bytes, str]]]
_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def find_cached_poster(directory: Path, source_id: str) -> Path | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", source_id):
        return None
    for extension in _EXTENSIONS.values():
        candidate = directory / f"{source_id}{extension}"
        if candidate.is_file():
            return candidate
    return None


async def cache_catalog_posters(
    items: list[Bangumi],
    directory: Path,
    *,
    fetch: PosterFetcher | None = None,
    max_concurrency: int = 4,
) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def store(item: Bangumi, fetcher: PosterFetcher) -> bool:
        if not item.poster_url or find_cached_poster(directory, item.source_id):
            return False
        try:
            async with semaphore:
                content, content_type = await fetcher(item.poster_url)
            media_type = content_type.split(";", 1)[0].casefold()
            extension = _EXTENSIONS.get(media_type)
            if extension is None or not content or len(content) > 8 * 1024 * 1024:
                return False
            temporary = directory / f".{item.source_id}{extension}.part"
            target = directory / f"{item.source_id}{extension}"
            temporary.write_bytes(content)
            temporary.replace(target)
            return True
        except (httpx.HTTPError, OSError, ValueError):
            return False

    async def run(fetcher: PosterFetcher) -> int:
        results = await asyncio.gather(*(store(item, fetcher) for item in items))
        return sum(results)

    if fetch is not None:
        return await run(fetch)

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        async def http_fetch(url: str) -> tuple[bytes, str]:
            response = await client.get(url)
            response.raise_for_status()
            return response.content, response.headers.get("content-type", "")

        return await run(http_fetch)
