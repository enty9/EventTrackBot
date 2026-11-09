from __future__ import annotations

import asyncio
import logging
import random
from urllib.parse import parse_qs, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

ENDPOINTS = (
    "https://html.duckduckgo.com/html/",
    "https://lite.duckduckgo.com/lite/",
)

BLOCKED_DOMAINS = {
    "youtube.com",
    "youtu.be",
    "vk.com",
    "t.me",
    "telegram.me",
    "instagram.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "ok.ru",
    "pinterest.com",
    "tiktok.com",
    "linkedin.com",
}

BLOCKED_SUFFIXES = (
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".zip",
    ".rar",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".mp4",
    ".mp3",
)


def _unwrap_url(href: str) -> str | None:
    href = href.strip()
    if not href:
        return None
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        query = parse_qs(parsed.query)
        target = query.get("uddg")
        if not target:
            return None
        href = unquote(target[0])
        parsed = urlparse(href)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None
    return href


def is_blocked(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.").split(":")[0]
    if any(host == domain or host.endswith("." + domain) for domain in BLOCKED_DOMAINS):
        return True
    path = parsed.path.lower()
    return path.endswith(BLOCKED_SUFFIXES)


def parse_results(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.select("a.result__a")
    if not anchors:
        anchors = soup.select("a.result-link")
    if not anchors:
        anchors = soup.select(".result__url")

    urls: list[str] = []
    for anchor in anchors:
        href = anchor.get("href")
        if not href:
            continue
        url = _unwrap_url(href)
        if not url or is_blocked(url):
            continue
        if url not in urls:
            urls.append(url)
    return urls


async def search_urls(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
    semaphore: asyncio.Semaphore,
) -> list[str]:
    async with semaphore:
        await asyncio.sleep(random.uniform(0.3, 1.2))
        for endpoint in ENDPOINTS:
            try:
                response = await client.get(
                    endpoint,
                    params={"q": query, "kl": "ru-ru"},
                    headers={"Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7"},
                    timeout=12.0,
                )
            except httpx.HTTPError as exc:
                log.debug("DuckDuckGo request failed (%s): %s", endpoint, exc)
                continue
            if response.status_code != 200:
                log.debug("DuckDuckGo returned %s for %s", response.status_code, query)
                continue
            urls = parse_results(response.text)
            if urls:
                return urls[:limit]
        return []
