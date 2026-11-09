from __future__ import annotations

import asyncio
import base64
import logging
import random
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from .ddg import is_blocked

log = logging.getLogger(__name__)

ENDPOINT = "https://www.bing.com/search"


def _decode_bing_url(href: str) -> str | None:
    href = href.strip()
    if not href:
        return None
    if href.startswith("//"):
        href = "https:" + href

    parsed = urlparse(href)
    if parsed.netloc.endswith("bing.com") and parsed.path.startswith("/ck/a"):
        query = parse_qs(parsed.query)
        target = query.get("u", [""])[0]
        if target.startswith("a1"):
            encoded = target[2:]
            encoded += "=" * ((4 - len(encoded) % 4) % 4)
            try:
                decoded = base64.urlsafe_b64decode(encoded).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                return None
            href = decoded
            parsed = urlparse(href)

    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None
    return href


def parse_results(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for item in soup.select("li.b_algo"):
        anchor = item.select_one("h2 a") or item.select_one("a[href]")
        if not anchor:
            continue
        url = _decode_bing_url(anchor.get("href") or "")
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
                params={"q": query, "setlang": "ru"},
                headers={"Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7"},
                timeout=12.0,
            )
        except httpx.HTTPError as exc:
            log.debug("Bing request failed: %s", exc)
            return []

        if response.status_code != 200:
            log.debug("Bing returned %s for %s", response.status_code, query)
            return []

        return parse_results(response.text)[:limit]
