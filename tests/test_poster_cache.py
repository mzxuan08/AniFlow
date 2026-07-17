import pytest

from aniflow.mikan import Bangumi
from aniflow.poster_cache import cache_catalog_posters, find_cached_poster


@pytest.mark.asyncio
async def test_poster_cache_downloads_to_local_file(tmp_path):
    calls = []

    async def fetch(url):
        calls.append(url)
        return b"webp-image", "image/webp"

    items = [Bangumi("3952", "Anime", "https://mikan/3952", "https://img/cover.webp")]

    count = await cache_catalog_posters(items, tmp_path, fetch=fetch)

    assert count == 1
    assert calls == ["https://img/cover.webp"]
    assert find_cached_poster(tmp_path, "3952").read_bytes() == b"webp-image"
