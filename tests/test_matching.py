from aniflow.matching import (
    classify_release,
    extract_episode,
    release_version,
    select_latest_1080p,
)
from aniflow.mikan import Release


def test_prefers_simplified_embedded_release():
    result = classify_release(
        "[Nix-Raws] Grand Blue S03E02 [1080p AVC AAC][简繁内封]"
    )

    assert result.accepted is True
    assert result.subtitle_kind == "简繁内封"
    assert result.score >= 80


def test_rejects_traditional_only_release():
    result = classify_release("[ANi] Grand Blue - 02 [1080P][CHT][MP4]")

    assert result.accepted is False
    assert result.reason == "仅检测到繁体字幕"


def test_rejects_raw_release():
    result = classify_release("[Ohys-Raws] Grand Blue - 02 [1080p][RAW]")

    assert result.accepted is False
    assert result.reason == "未检测到简体字幕"


def test_extracts_season_and_episode():
    assert extract_episode("Grand Blue S03E02 1080p") == (3, 2)


def test_extracts_plain_episode_number():
    assert extract_episode("碧蓝之海 第三季 - 02 [简中]") == (None, 2)


def test_episode_separator_wins_over_number_in_romanized_title():
    title = (
        "[Nekomoe kissaten&LoliHouse] 20 Seiki Denki Mokuroku - 02 "
        "[WebRip 1080p HEVC-10bit AAC ASSx2].mkv"
    )

    assert extract_episode(title) == (None, 2)


def test_extracts_local_and_absolute_episode_number():
    assert extract_episode("史莱姆第四季 [14(86)][简体][1080P]") == (None, 14)


def test_extracts_bracketed_episode_number():
    assert extract_episode("Someya-san [01][1080P][简体内嵌]") == (None, 1)


def test_selects_latest_1080p_simplified_release():
    releases = [
        Release("1", "Anime - 13 [简体][1080P][MP4]", "https://x/1", "https://x/e1"),
        Release("2", "Anime - 14 [简体][720P][MP4]", "https://x/2", "https://x/e2"),
        Release("3", "Anime - 14 [简繁内封][1080P][HEVC]", "https://x/3", "https://x/e3"),
        Release("4", "Anime - 14 [简体内嵌][1080P][MP4]", "https://x/4", "https://x/e4"),
    ]

    selected = select_latest_1080p(releases)

    assert selected is not None
    assert selected.guid == "4"


def test_prefers_pure_simplified_embedded_over_mixed_subtitles():
    releases = [
        Release("mixed", "Someya-san [01][1080P][简繁内封]", "https://x/m", "https://x/em"),
        Release("traditional", "Someya-san [01][1080P][繁体内嵌]", "https://x/t", "https://x/et"),
        Release("simplified", "Someya-san [01][1080P][简体内嵌]", "https://x/s", "https://x/es"),
    ]

    selected = select_latest_1080p(releases)

    assert selected is not None
    assert selected.guid == "simplified"


def test_extracts_release_version_and_defaults_to_one():
    assert release_version("Anime - 01 v2 [1080p][简体]") == 2
    assert release_version("Anime - 01 V3 [1080p][简体]") == 3
    assert release_version("Anime - 01 [1080p][简体]") == 1


def test_v2_wins_over_better_scored_unversioned_release():
    releases = [
        Release("v1", "Anime - 01 [1080P][简体内嵌][MP4][AVC][AAC]", "https://x/1", "https://x/e1"),
        Release("v2", "Anime - 01 v2 [1080P][简日内嵌]", "https://x/2", "https://x/e2"),
    ]

    selected = select_latest_1080p(releases)

    assert selected is not None
    assert selected.guid == "v2"
