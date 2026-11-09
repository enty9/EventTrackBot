from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..cities import normalize_city

log = logging.getLogger(__name__)

FREEEVENT_SLUGS = {
    "москва": "moscow",
    "санкт-петербург": "spb",
    "новосибирск": "novosibirsk",
    "екатеринбург": "ekaterinburg",
    "казань": "kazan",
    "самара": "samara",
    "ростов-на-дону": "rostov",
    "владивосток": "vladivostok",
}

HACKLIST_SLUGS = {
    "москва": "moscow",
    "санкт-петербург": "spb",
}

ICT2GO_SLUGS = {
    "москва": "moscow",
    "санкт-петербург": "sain-petersburg",
    "новосибирск": "novosibirsk",
    "екатеринбург": "ekaterinburg",
    "казань": "kazan",
    "нижний новгород": "nizhny_novgorod",
    "самара": "samara",
    "краснодар": "krasnodar",
    "воронеж": "voronezh",
    "пермь": "perm",
    "уфа": "ufa",
    "челябинск": "chelyabinsk",
    "омск": "omsk",
    "красноярск": "krasnoyarsk",
    "тюмень": "tyumen",
    "иркутск": "irkutsk",
    "владивосток": "vladivostok",
    "волгоград": "volgograd",
    "томск": "tomsk",
    "барнаул": "barnaul",
    "ульяновск": "ulyanovsk",
    "ижевск": "izhevsk",
    "ярославль": "yaroslavl",
    "тула": "tula",
    "кемерово": "kemerovo",
    "сочи": "sochi",
    "ставрополь": "stavropol",
    "севастополь": "sevastopol",
}

_ICT_EVENT_PATH_RE = re.compile(r"^/events/\d+/?$")
_HACKLIST_EVENT_PATH_RE = re.compile(r"^/itevents/[^/]+/?$")
MAX_ICT_EVENTS = 10
MAX_HACKLIST_EVENTS = 10


async def _get_html(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        response = await client.get(url, timeout=12.0)
    except httpx.HTTPError as exc:
        log.debug("Не удалось загрузить источник %s: %s", url, exc)
        return None
    if response.status_code != 200:
        return None
    content_type = response.headers.get("content-type", "").lower()
    if content_type and "html" not in content_type:
        return None
    return response.text


def _ict_event_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for anchor in soup.select("a[href]"):
        href = anchor.get("href") or ""
        path = urlparse(href).path
        if not _ICT_EVENT_PATH_RE.fullmatch(path):
            continue
        url = urljoin(base_url, href)
        if url not in urls:
            urls.append(url)
        if len(urls) >= MAX_ICT_EVENTS:
            break
    return urls


async def _ict2go_urls(client: httpx.AsyncClient, slug: str) -> list[str]:
    region_url = f"https://ict2go.ru/regions/{slug}/"
    html = await _get_html(client, region_url)
    if not html:
        return []
    return [region_url, *_ict_event_links(html, region_url)]


async def _hacklist_urls(client: httpx.AsyncClient, slug: str) -> list[str]:
    listing_url = f"https://hacklist.ru/events/{slug}/"
    html = await _get_html(client, listing_url)
    if not html:
        return []
    return _hacklist_links(html, listing_url)


def _hacklist_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    for anchor in soup.select("a[href]"):
        href = anchor.get("href") or ""
        path = urlparse(href).path
        if not _HACKLIST_EVENT_PATH_RE.fullmatch(path):
            continue
        url = urljoin(base_url, href)
        if url not in urls:
            urls.append(url)
        if len(urls) >= MAX_HACKLIST_EVENTS:
            break
    return urls


async def discover_direct(client: httpx.AsyncClient, city: str) -> list[str]:
    key = normalize_city(city).lower()
    urls: list[str] = []

    freeevent_slug = FREEEVENT_SLUGS.get(key)
    if freeevent_slug:
        urls.append(f"https://freeitevent.ru/events/{freeevent_slug}/")

    tasks = []
    ict2go_slug = ICT2GO_SLUGS.get(key)
    if ict2go_slug:
        tasks.append(_ict2go_urls(client, ict2go_slug))
    hacklist_slug = HACKLIST_SLUGS.get(key)
    if hacklist_slug:
        tasks.append(_hacklist_urls(client, hacklist_slug))

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                log.debug("Прямой источник недоступен: %s", result)
                continue
            urls.extend(result)

    seen: set[str] = set()
    unique: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        unique.append(url)
    return unique
