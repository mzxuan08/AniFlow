from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://mikanani.me"
CLASSIC_RSS_URL = f"{BASE_URL}/RSS/Classic"


@dataclass(frozen=True, slots=True)
class Bangumi:
    source_id: str
    title: str
    url: str
    poster_url: str | None = None


@dataclass(frozen=True, slots=True)
class Release:
    guid: str
    title: str
    torrent_url: str
    page_url: str
    published: str | None = None


class _CatalogParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current: dict[str, str | None] | None = None
        self.items: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "a" and re.fullmatch(r"/Home/Bangumi/\d+", attributes.get("href", "")):
            self.current = {"href": attributes["href"], "poster": None, "text": ""}
        elif tag == "img" and self.current is not None and attributes.get("src"):
            self.current["poster"] = attributes["src"]

    def handle_data(self, data: str) -> None:
        if self.current is not None:
            self.current["text"] = f"{self.current['text'] or ''} {data}".strip()

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.current is not None:
            self.items.append(self.current)
            self.current = None


def parse_catalog(html: str) -> list[Bangumi]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[Bangumi] = []
    seen: set[str] = set()
    for link in soup.find_all("a", href=re.compile(r"^/Home/Bangumi/\d+$")):
        href = link.get("href", "")
        source_id = href.rsplit("/", 1)[-1]
        title = " ".join((link.get("title") or link.get_text(" ", strip=True)).split())
        if not title or source_id in seen:
            continue
        seen.add(source_id)
        container = link.find_parent("li")
        lazy_poster = container.select_one("[data-src]") if container else None
        nested_image = link.find("img")
        poster_path = (
            lazy_poster.get("data-src")
            if lazy_poster is not None
            else nested_image.get("src") if nested_image is not None else None
        )
        poster = urljoin(BASE_URL, poster_path) if poster_path else None
        results.append(Bangumi(source_id, title, urljoin(BASE_URL, href), poster))
    return results


def parse_rss(xml: str) -> list[Release]:
    root = ET.fromstring(xml)
    releases: list[Release] = []
    for item in root.findall("./channel/item"):
        enclosure = item.find("enclosure")
        torrent_url = enclosure.get("url", "") if enclosure is not None else ""
        guid = item.findtext("guid") or torrent_url
        title = item.findtext("title") or ""
        page_url = item.findtext("link") or guid
        if title and guid and torrent_url:
            releases.append(Release(guid, title, torrent_url, page_url, item.findtext("pubDate")))
    return releases


def parse_bangumi_releases(html: str) -> list[Release]:
    soup = BeautifulSoup(html, "html.parser")
    releases: list[Release] = []
    seen: set[str] = set()
    for episode_link in soup.select('a[href*="/Home/Episode/"]'):
        page_url = urljoin(BASE_URL, episode_link.get("href", ""))
        if not page_url or page_url in seen:
            continue
        download_link = episode_link.find_next("a", href=re.compile(r"/Download/.+\.torrent$"))
        if download_link is None:
            continue
        title = " ".join(episode_link.get_text(" ", strip=True).split())
        torrent_url = urljoin(BASE_URL, download_link.get("href", ""))
        if title and torrent_url:
            seen.add(page_url)
            releases.append(Release(page_url, title, torrent_url, page_url))
    return releases


class MikanClient:
    def __init__(self, timeout: float = 20) -> None:
        self.timeout = timeout

    async def catalog(self) -> list[Bangumi]:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(BASE_URL)
            response.raise_for_status()
            return parse_catalog(response.text)

    async def rss(self) -> list[Release]:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(CLASSIC_RSS_URL)
            response.raise_for_status()
            return parse_rss(response.text)

    async def torrent(self, url: str) -> bytes:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

    async def bangumi_releases(self, source_id: str) -> list[Release]:
        url = f"{BASE_URL}/Home/Bangumi/{source_id}"
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return parse_bangumi_releases(response.text)
