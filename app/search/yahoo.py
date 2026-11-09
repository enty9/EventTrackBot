from __future__ import annotations

import asyncio
import logging
import random
import re
from urllib.parse import unquote, urlparse

import httpx
from bs4 import BeautifulSoup

from .ddg import is_blocked

log = logging.getLogger(__name__)

ENDPOINT = "https://search.yahoo.com/search"
_YAHOO_REDIRECT_RE = re.compile(r"/RU=([^/]+)/")


def _decode_yahoo_url(href: str) -> str | None:
    href = href.strip()
    if not href:
        return None
    if href.startswith("//"):
        href = "https:" + href

    parsed = urlparse(href)
    if parsed.netloc.endswith("yahoo.com"):
        match = _YAHOO_REDIRECT_RE.search(parsed.path)
        if match:
            href = unquote(match.group(1))
            parsed = urlparse(href)

    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None
    return href


def parse_results(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for item in soup.select("div.algo"):
        anchor = item.select_one("a[href]")
        if not anchor:
            continue
        url = _decode_yahoo_url(anchor.get("href") or "")
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
        await asyncio.sleep(random.uniform(0.2, 0.9))
        try:
            response = await client.get(
                ENDPOINT,
                params={"p": query},
                headers={"Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7"},
                timeout=12.0,
            )
        except httpx.HTTPError as exc:
            log.debug("Yahoo request failed: %s", exc)
            return []

        if response.status_code != 200:
            log.debug("Yahoo returned %s for %s", response.status_code, query)
            return []

        return parse_results(response.text)[:limit]
