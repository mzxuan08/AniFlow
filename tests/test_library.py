import pytest

from aniflow.library import MediaLibraryCache, resolve_media_path, scan_library


def test_library_groups_anime_and_sorts_episodes(tmp_path):
    anime = tmp_path / "碧蓝之海 第三季"
    anime.mkdir()
    (anime / "Grand Blue - 02 [1080P].mp4").write_bytes(b"22")
    (anime / "Grand Blue - 01 [1080P].mkv").write_bytes(b"1")

    groups = scan_library(tmp_path)

    assert groups[0].title == "碧蓝之海 第三季"
    assert [item.episode for item in groups[0].episodes] == [2, 1]
    assert groups[0].episodes[0].size == 2


def test_library_scan_excludes_hidden_relative_paths(tmp_path):
    anime = tmp_path / "Anime"
    anime.mkdir()
    (anime / "Anime - 01 [1080P].mp4").write_bytes(b"1")
    (anime / "Anime - 02 [1080P].mp4").write_bytes(b"2")

    groups = scan_library(tmp_path, hidden={"Anime/Anime - 01 [1080P].mp4"})

    assert [item.episode for item in groups[0].episodes] == [2]


def test_media_path_cannot_escape_download_root(tmp_path):
    outside = tmp_path.parent / "outside.mp4"
    outside.write_bytes(b"keep")

    with pytest.raises(ValueError):
        resolve_media_path(tmp_path, "../outside.mp4")

    assert outside.read_bytes() == b"keep"


@pytest.mark.asyncio
async def test_media_library_cache_reuses_scan_until_invalidated(tmp_path):
    calls = []

    def scanner(root, hidden=None, unavailable=None):
        calls.append((root, hidden, unavailable))
        return []

    cache = MediaLibraryCache(scanner=scanner, ttl_seconds=60)

    assert await cache.get(tmp_path, {"hidden.mp4"}, set()) == []
    assert await cache.get(tmp_path, {"hidden.mp4"}, set()) == []
    assert len(calls) == 1

    cache.invalidate()
    assert await cache.get(tmp_path, {"hidden.mp4"}, set()) == []
    assert len(calls) == 2
