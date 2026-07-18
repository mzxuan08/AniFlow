from aniflow.experience import build_episode_overview


def test_episode_overview_reports_only_released_missing_episodes():
    overview = build_episode_overview(
        "Anime",
        release_titles=[
            "[Group] Anime - 01 [1080p][简体]",
            "[Group] Anime - 02 [1080p][简体]",
            "[Group] Anime - 03 [1080p][简体]",
        ],
        task_titles=["Anime - 03 [1080p][简体]"],
        media_names=["Anime - 01.mp4"],
    )

    assert overview.latest_released == 3
    assert overview.downloaded == {1}
    assert overview.active == {3}
    assert overview.missing == {2}


def test_episode_overview_ignores_other_series_and_unreleased_future():
    overview = build_episode_overview(
        "Anime",
        release_titles=[
            "[Group] Cartoon - 12 [1080p][简体]",
            "[Group] Anime - 04 [1080p][简体]",
        ],
        task_titles=[],
        media_names=["Anime - 04.mp4"],
    )

    assert overview.latest_released == 4
    assert overview.missing == set()
