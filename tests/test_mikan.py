from aniflow.mikan import parse_bangumi_releases, parse_catalog, parse_rss


def test_parse_catalog_extracts_unique_bangumi():
    html = """
    <a href="/Home/Bangumi/4014"><img src="/images/4014.jpg">碧蓝之海 第三季</a>
    <a href="/Home/Bangumi/4014">碧蓝之海 第三季</a>
    <a href="/Home/Bangumi/4001"><img src="https://img/4001.jpg">另一部动画</a>
    """

    items = parse_catalog(html)

    assert [(item.source_id, item.title) for item in items] == [
        ("4014", "碧蓝之海 第三季"),
        ("4001", "另一部动画"),
    ]
    assert items[0].poster_url == "https://mikanani.me/images/4014.jpg"


def test_parse_catalog_reads_current_mikan_lazy_poster_structure():
    html = """
    <ul><li>
      <span data-src="/images/Bangumi/202604/cover.jpg?width=400&amp;height=400&amp;format=webp"
            class="js-expand_bangumi b-lazy" data-bangumiid="3952"></span>
      <div class="an-info"><a href="/Home/Bangumi/3952" class="an-text"
        title="关于我转生变成史莱姆这档事 第四季">关于我转生变成史莱姆这档事 第四季</a></div>
    </li></ul>
    """

    items = parse_catalog(html)

    assert len(items) == 1
    assert items[0].source_id == "3952"
    assert items[0].poster_url == (
        "https://mikanani.me/images/Bangumi/202604/cover.jpg?width=400&height=400&format=webp"
    )


def test_parse_rss_extracts_torrent_and_guid():
    xml = """<?xml version="1.0"?><rss><channel><item>
      <title>[Group] Anime - 02 [简中][MP4]</title>
      <guid>https://mikanani.me/Home/Episode/abc</guid>
      <link>https://mikanani.me/Home/Episode/abc</link>
      <enclosure url="https://mikanani.me/Download/abc.torrent" length="123" type="application/x-bittorrent" />
      <pubDate>Tue, 14 Jul 2026 00:01:00 GMT</pubDate>
    </item></channel></rss>"""

    releases = parse_rss(xml)

    assert releases[0].guid.endswith("/abc")
    assert releases[0].torrent_url.endswith("abc.torrent")
    assert releases[0].title.startswith("[Group]")


def test_parse_bangumi_releases_pairs_episode_and_torrent_links():
    html = """
    <div><a href="/Home/Episode/hash1">Anime - 14 [简体][1080P][MP4]</a>
    <a href="/Download/20260717/hash1.torrent">下载</a></div>
    <div><a href="/Home/Episode/hash1">Anime - 14 [简体][1080P][MP4]</a>
    <a href="/Download/20260717/hash1.torrent">下载</a></div>
    """

    releases = parse_bangumi_releases(html)

    assert len(releases) == 1
    assert releases[0].guid.endswith("/hash1")
    assert releases[0].torrent_url.endswith("hash1.torrent")
