from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timedelta, timezone

import httpx

from ..cities import city_variants
from ..models import Event
from ..money import normalize_currency
from ..spheres import DEFAULT_SPHERE, Sphere, get_sphere
from ..timeutil import MOSCOW, as_utc
from .bing import search_urls as bing_search
from .currency import CurrencyConverter
from .ddg import is_blocked
from .ddg import search_urls as ddg_search
from .direct import discover_direct
from .extract import extract_events
from .yahoo import search_urls as yahoo_search

log = logging.getLogger(__name__)

MAX_PAGE_BYTES = 4 * 1024 * 1024
DISCOVERY_TIMEOUT = 35.0
PAGE_BATCH_TIMEOUT = 55.0
PAGE_TIMEOUT = 12.0
PAGE_CONCURRENCY = 8

_LIST_TITLE_RE = re.compile(
    r"^\s*(?:it|ит)\s*[-–—:]?\s*(?:конференции|мероприятия|события|афиша)\b"
    r"|(?:афиша|календарь|подборка|список)\s+(?:it|ит|мероприятий|событий|конференций)"
    r"|\bконференции\s+и\s+мероприятия\b"
    r"|\bмероприятия\s+в\s+(?:россии|москве|санкт-петербурге)\b",
    re.IGNORECASE,
)


class EventSearcher:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        results_per_query: int = 10,
        max_urls: int = 30,
        max_events: int = 50,
        cache_ttl: int = 600,
    ) -> None:
        self._client = client
        self._results_per_query = results_per_query
        self._max_urls = max_urls
        self._max_events = max_events
        self._cache_ttl = cache_ttl
        self._converter = CurrencyConverter(client)
        self._cache: dict[str, tuple[float, list[Event]]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _queries(self, city: str, sphere: Sphere) -> list[str]:
        year = datetime.now(MOSCOW).year
        return [
            template.format(city=city, year=year) for template in sphere.queries
        ]

    async def search(
        self, city: str, sphere_key: str = DEFAULT_SPHERE
    ) -> list[Event]:
        sphere = get_sphere(sphere_key)
        city = city.strip()
        cache_key = f"{sphere.key}:{city}"
        now = time.monotonic()
        cached = self._cache.get(cache_key)
        if cached and now - cached[0] < self._cache_ttl:
            return list(cached[1])

        lock = self._locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            cached = self._cache.get(cache_key)
            if cached and now - cached[0] < self._cache_ttl:
                return list(cached[1])

            try:
                events = await self._search_uncached(city, sphere)
            except Exception:
                log.exception(
                    "Ошибка поиска мероприятий в городе %s (сфера %s)",
                    city,
                    sphere.title,
                )
                events = []

            self._cache[cache_key] = (time.monotonic(), events)
            if len(self._cache) > 50:
                oldest = min(self._cache.items(), key=lambda item: item[1][0])[0]
                self._cache.pop(oldest, None)
            return list(events)

    async def _search_uncached(self, city: str, sphere: Sphere) -> list[Event]:
        urls = await self._discover(city, sphere)
        if not urls:
            log.info("Поиск не вернул ссылок для города %s", city)
            return []

        semaphore = asyncio.Semaphore(PAGE_CONCURRENCY)

        async def load(url: str) -> tuple[str, list[Event]]:
            async with semaphore:
                html = await self._fetch(url)
            if not html:
                return url, []
            try:
                return url, extract_events(html, url)
            except Exception:
                log.exception("Не удалось разобрать страницу %s", url)
                return url, []

        load_tasks = {
            asyncio.create_task(load(url), name=f"load:{url}"): url for url in urls
        }
        try:
            done, pending = await asyncio.wait(
                load_tasks, timeout=PAGE_BATCH_TIMEOUT
            )
        except asyncio.CancelledError:
            for task in load_tasks:
                task.cancel()
            await asyncio.gather(*load_tasks, return_exceptions=True)
            raise

        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        pages: list[tuple[str, list[Event]]] = []
        for task in done:
            try:
                pages.append(task.result())
            except Exception:
                log.debug("Страница не обработана: %s", load_tasks[task], exc_info=True)

        now = datetime.now(timezone.utc)
        events: list[Event] = []
        for _url, page_events in pages:
            for event in page_events:
                if self._is_relevant(event, city, now, sphere):
                    events.append(event)

        await self._enrich_events(events)
        events = self._dedupe_events(events)
        await self._convert_prices(events)
        events.sort(
            key=lambda event: (
                event.start is None,
                as_utc(event.start)
                if event.start
                else datetime.max.replace(tzinfo=timezone.utc),
                event.title.lower(),
            )
        )
        return events[: self._max_events]

    async def _discover(self, city: str, sphere: Sphere) -> list[str]:
        tasks = []
        if sphere.direct:
            tasks.append(
                asyncio.wait_for(discover_direct(self._client, city), DISCOVERY_TIMEOUT)
            )
        tasks.append(
            asyncio.wait_for(self._search_discover(city, sphere), DISCOVERY_TIMEOUT)
        )
        results = await asyncio.gather(*tasks, return_exceptions=True)

        urls: list[str] = []
        for result in results:
            if isinstance(result, BaseException):
                log.debug("Источник недоступен: %s", result)
                continue
            for url in result:
                if url not in urls:
                    urls.append(url)
                if len(urls) >= self._max_urls:
                    return urls
        return urls

    async def _search_discover(self, city: str, sphere: Sphere) -> list[str]:
        semaphore = asyncio.Semaphore(2)

        async def run_query(query: str) -> list[str]:
            for provider in (bing_search, yahoo_search, ddg_search):
                urls = await provider(
                    self._client, query, self._results_per_query, semaphore
                )
                if urls:
                    return urls
            return []

        tasks = [run_query(query) for query in self._queries(city, sphere)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        urls: list[str] = []
        for result in results:
            if isinstance(result, BaseException):
                log.debug("Поисковая выдача недоступна: %s", result)
                continue
            for url in result:
                if url not in urls:
                    urls.append(url)
                if len(urls) >= self._max_urls:
                    return urls
        return urls

    async def _fetch(self, url: str) -> str | None:
        try:
            response = await self._client.get(url, timeout=PAGE_TIMEOUT)
        except httpx.HTTPError as exc:
            log.debug("Не удалось загрузить %s: %s", url, exc)
            return None

        if response.status_code != 200:
            return None
        content_type = response.headers.get("content-type", "").lower()
        if content_type and "html" not in content_type and "xml" not in content_type:
            return None
        if len(response.content) > MAX_PAGE_BYTES:
            return None
        try:
            return response.text
        except (UnicodeDecodeError, LookupError):
            return None

    def _is_relevant(
        self, event: Event, city: str, now: datetime, sphere: Sphere
    ) -> bool:
        if _LIST_TITLE_RE.search(event.title):
            return False

        if event.end:
            if event.end.hour or event.end.minute:
                if as_utc(event.end) < now - timedelta(minutes=30):
                    return False
            elif as_utc(event.end).date() < now.astimezone(MOSCOW).date():
                return False

        if event.start and as_utc(event.start) < now - timedelta(hours=12):
            return False

        headline = f"{event.title} {event.description} {event.event_type}"
        if sphere.keywords is not None and not sphere.keywords.search(headline):
            return False

        return self._city_matches(event, city)

    @staticmethod
    def _city_matches(event: Event, city: str) -> bool:
        variants = city_variants(city)

        def hit(text: str) -> bool:
            lowered = text.lower()
            return any(variant in lowered for variant in variants)

        if event.city and hit(event.city):
            return True
        if event.address and hit(event.address):
            return True
        if event.venue and hit(event.venue):
            return True
        if event.city:
            return False
        if event.address or event.venue:
            return hit(event.page_text[:6000])
        return hit(f"{event.title} {event.description} {event.page_text[:4000]}")

    @staticmethod
    def _title_key(title: str) -> str:
        return re.sub(r"\W+", "", title.lower())[:80]

    async def _enrich_events(self, events: list[Event]) -> None:
        targets = [
            event
            for event in events
            if event.official_url
            and not is_blocked(event.official_url)
            and event.official_url != event.page_url
            and (
                event.start is None
                or not event.image
                or event.price is None
                or not event.description
            )
        ][:8]
        if not targets:
            return

        semaphore = asyncio.Semaphore(4)

        async def enrich(event: Event) -> None:
            detail_url = event.official_url
            async with semaphore:
                html = await self._fetch(detail_url)
            if not html:
                return
            try:
                candidates = extract_events(html, detail_url)
            except Exception:
                log.debug("Не удалось обогатить %s", detail_url, exc_info=True)
                return
            if not candidates:
                return
            key = self._title_key(event.title)
            match = next(
                (candidate for candidate in candidates if self._title_key(candidate.title) == key),
                None,
            )
            if match is None and len(candidates) == 1:
                match = candidates[0]
            if match is None:
                return

            for field_name in (
                "start",
                "end",
                "image",
                "description",
                "price",
                "currency",
                "registration_url",
                "age",
                "organizer",
                "attendance",
                "venue",
                "address",
                "city",
                "is_free",
            ):
                if not getattr(event, field_name) and getattr(match, field_name):
                    setattr(event, field_name, getattr(match, field_name))

        await asyncio.gather(*(enrich(event) for event in targets), return_exceptions=True)

    @classmethod
    def _dedupe_events(cls, events: list[Event]) -> list[Event]:
        seen: set[tuple[str, str]] = set()
        unique: list[Event] = []
        for event in events:
            key = (
                cls._title_key(event.title),
                event.start.date().isoformat() if event.start else "",
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(event)
        return unique

    async def _convert_prices(self, events: list[Event]) -> None:
        for event in events:
            if event.price is None or event.price <= 0:
                continue
            code = normalize_currency(event.currency)
            if not code or code == "RUB":
                event.price_rub = event.price
                continue
            converted = await self._converter.to_rub(event.price, code)
            if converted is not None:
                event.price_rub = converted
