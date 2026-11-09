from __future__ import annotations

import html as html_lib
import json
import re
from collections.abc import Iterable
from datetime import date
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..models import Event
from ..money import normalize_currency, parse_price
from ..timeutil import parse_date_text, parse_iso_datetime

_EVENT_TYPES = {
    "Event",
    "BusinessEvent",
    "ChildrensEvent",
    "ComedyEvent",
    "ConferenceEvent",
    "CourseInstance",
    "DanceEvent",
    "DeliveryEvent",
    "EducationEvent",
    "EventSeries",
    "ExhibitionEvent",
    "Festival",
    "FoodEvent",
    "Hackathon",
    "LiteraryEvent",
    "Meetup",
    "MusicEvent",
    "PublicationEvent",
    "SaleEvent",
    "ScreeningEvent",
    "SocialEvent",
    "SportsEvent",
    "TheaterEvent",
    "VisualArtsEvent",
}

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_HTML_COMMENT_RE = re.compile(r"^\s*<!--|-->\s*$")
_PRICE_IN_TEXT_RE = re.compile(
    r"(?<!\d)(\d[\d\s\xa0]{0,9})\s*(?:₽|руб(?:\.|лей|ля|ль)?)(?!\w)",
    re.IGNORECASE,
)
_EVENT_WORD_RE = re.compile(
    r"мероприят|конференц|хакатон|митап|meetup|воркшоп|семинар|форум|"
    r"фестивал|лекц|интенсив|курс|олимпиад|чемпионат|питч|workshop",
    re.IGNORECASE,
)


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def clean_text(value: object, max_len: int | None = None) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        value = " ".join(clean_text(item) for item in value)
    elif isinstance(value, dict):
        value = (
            value.get("name")
            or value.get("headline")
            or value.get("@value")
            or value.get("value")
            or value.get("url")
            or ""
        )
    text = html_lib.unescape(str(value))
    text = _TAG_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip()
    if max_len and len(text) > max_len:
        text = text[:max_len].rstrip() + "…"
    return text


def _iter_jsonld(soup: BeautifulSoup) -> Iterable[object]:
    for script in soup.find_all("script"):
        script_type = (script.get("type") or "").lower()
        if "ld+json" not in script_type:
            continue
        raw = script.string if script.string is not None else script.get_text()
        if not raw:
            continue
        raw = _HTML_COMMENT_RE.sub("", raw.strip()).strip()
        if not raw:
            continue
        try:
            yield json.loads(raw, strict=False)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue


def _walk(node: object, depth: int = 0) -> Iterable[dict]:
    if depth > 8:
        return
    if isinstance(node, dict):
        yield node
        for key in ("@graph", "mainEntity", "itemListElement", "hasPart", "item"):
            child = node.get(key)
            if child:
                yield from _walk(child, depth + 1)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item, depth + 1)


def _is_event_node(node: dict) -> bool:
    types = node.get("@type")
    if isinstance(types, str):
        types = [types]
    if not isinstance(types, list):
        return False
    for type_name in types:
        if not isinstance(type_name, str):
            continue
        short = re.split(r"[/#]", type_name)[-1]
        if short in _EVENT_TYPES or short.endswith("Event"):
            return True
    return False


def _first_url(value: object) -> str:
    for item in _as_list(value):
        if isinstance(item, str) and item.strip():
            return item.strip()
        if isinstance(item, dict):
            candidate = item.get("url") or item.get("contentUrl")
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return ""


def _parse_location(location: object) -> tuple[str, str, str]:
    names: list[str] = []
    addresses: list[str] = []
    cities: list[str] = []

    for item in _as_list(location):
        if isinstance(item, str):
            text = clean_text(item)
            if text:
                addresses.append(text)
            continue
        if not isinstance(item, dict):
            continue

        name = clean_text(item.get("name"))
        if name:
            names.append(name)

        address = item.get("address")
        if isinstance(address, str):
            text = clean_text(address)
            if text:
                addresses.append(text)
        elif isinstance(address, dict):
            locality = clean_text(address.get("addressLocality"))
            region = clean_text(address.get("addressRegion"))
            street = clean_text(address.get("streetAddress"))
            postal = clean_text(address.get("postalCode"))
            line = ", ".join(part for part in (postal, region, locality, street) if part)
            if line:
                addresses.append(line)
            if locality:
                cities.append(locality)

    return (
        ", ".join(dict.fromkeys(names)),
        ", ".join(dict.fromkeys(addresses)),
        ", ".join(dict.fromkeys(cities)),
    )


def _parse_offers(offers: object) -> tuple[float | None, str, str, bool]:
    prices: list[float] = []
    currency = ""
    registration_url = ""

    for offer in _as_list(offers):
        if not isinstance(offer, dict):
            continue

        for key in ("price", "lowPrice"):
            price = parse_price(offer.get(key))
            if price is not None:
                prices.append(price)
                break

        if not currency:
            currency = normalize_currency(offer.get("priceCurrency"))

        if not registration_url:
            url = offer.get("url")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                registration_url = url

    if not prices:
        return None, currency, registration_url, False

    unique_prices = sorted(set(prices))
    price = unique_prices[0]
    price_from = len(unique_prices) > 1
    return price, currency, registration_url, price_from


def _format_age(node: dict) -> str:
    for key in ("typicalAgeRatingFrom", "typicalAgeRatingTo", "ageRating"):
        value = node.get(key)
        if value is None or isinstance(value, (dict, list)):
            continue
        text = clean_text(value)
        if text:
            if text.isdigit():
                return f"{text}+"
            return text
    return ""


def _node_to_event(node: dict, url: str, page_text: str) -> Event | None:
    title = clean_text(node.get("name") or node.get("headline"), max_len=300)
    if not title:
        return None

    status = clean_text(node.get("eventStatus"))
    if "Cancelled" in status or "Postponed" in status:
        return None

    description = clean_text(node.get("description"), max_len=2000)
    start = parse_iso_datetime(clean_text(node.get("startDate")))
    end = parse_iso_datetime(clean_text(node.get("endDate")))
    venue, address, city = _parse_location(node.get("location"))
    price, currency, registration_url, price_from = _parse_offers(node.get("offers"))

    is_free: bool | None = None
    if node.get("isAccessibleForFree") is True:
        price = 0.0
        is_free = True
    elif price is not None:
        is_free = price <= 0

    image = _first_url(node.get("image"))
    if image:
        image = urljoin(url, image)

    organizer = ""
    organizer_node = node.get("organizer")
    if isinstance(organizer_node, dict):
        organizer = clean_text(organizer_node.get("name"))
    elif isinstance(organizer_node, str):
        organizer = clean_text(organizer_node)

    types = node.get("@type")
    if isinstance(types, str):
        types = [types]
    event_type = ""
    if isinstance(types, list):
        event_type = ", ".join(
            re.split(r"[/#]", item)[-1] for item in types if isinstance(item, str)
        )

    attendance = ""
    attendance_mode = clean_text(node.get("eventAttendanceMode"))
    if attendance_mode:
        if "Mixed" in attendance_mode:
            attendance = "онлайн + офлайн"
        elif "Online" in attendance_mode:
            attendance = "онлайн"
        elif "Offline" in attendance_mode:
            attendance = "офлайн"

    official_url = ""
    raw_official_url = clean_text(node.get("url"))
    if raw_official_url:
        candidate = urljoin(url, raw_official_url)
        if candidate.rstrip("/") != url.rstrip("/"):
            official_url = candidate

    return Event(
        title=title,
        url=url,
        source=urlparse(url).netloc.lower().removeprefix("www."),
        official_url=official_url,
        description=description,
        start=start,
        end=end,
        city=city,
        venue=venue,
        address=address,
        price=price,
        currency=currency,
        price_from=price_from,
        image=image,
        organizer=organizer,
        age=_format_age(node),
        is_free=is_free,
        registration_url=registration_url,
        event_type=event_type,
        attendance=attendance,
        page_url=url,
        page_text=page_text[:5000],
    )


def _meta(soup: BeautifulSoup, *, property_name: str | None = None, name: str | None = None) -> str:
    attrs: dict[str, str] = {}
    if property_name:
        attrs["property"] = property_name
    if name:
        attrs["name"] = name
    tag = soup.find("meta", attrs=attrs)
    if not tag:
        return ""
    return clean_text(tag.get("content"))


def _clean_page_title(title: str) -> str:
    cleaned = re.sub(
        r"\s+[-–—|]\s+[A-Za-zА-Яа-я0-9.-]+\.(?:ru|com|org|net|io|media|agency)\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\s+\d{1,2}\.\d{1,2}\.\d{2,4}"
        r"(?:\s*[-–—]\s*\d{1,2}\.\d{1,2}\.\d{2,4})?\s*$",
        "",
        cleaned,
    )
    return cleaned.strip(" -–—|") or title


def _fallback_event(soup: BeautifulSoup, url: str, page_text: str) -> Event | None:
    title = clean_text(_meta(soup, property_name="og:title"), max_len=300)
    if not title and soup.h1:
        title = clean_text(soup.h1.get_text(" ", strip=True), max_len=300)
    if not title and soup.title:
        title = clean_text(soup.title.get_text(" ", strip=True), max_len=300)
    title = _clean_page_title(title)
    if not title:
        return None

    description = clean_text(
        _meta(soup, property_name="og:description") or _meta(soup, name="description"),
        max_len=2000,
    )

    start = None
    for tag in soup.select("time[datetime]"):
        start = parse_iso_datetime(tag.get("datetime"))
        if start:
            break
    if not start:
        start = parse_date_text(page_text, default_year=date.today().year)
    if not start:
        return None

    combined = f"{title} {description} {page_text[:3000]}"
    if not _EVENT_WORD_RE.search(combined):
        return None

    image = _meta(soup, property_name="og:image")
    if image:
        image = urljoin(url, image)

    price = None
    price_match = _PRICE_IN_TEXT_RE.search(page_text)
    if price_match:
        price = parse_price(price_match.group(1))

    return Event(
        title=title,
        url=url,
        source=urlparse(url).netloc.lower().removeprefix("www."),
        description=description,
        start=start,
        price=price,
        currency="RUB" if price is not None else "",
        image=image,
        is_free=(price <= 0) if price is not None else None,
        page_url=url,
        page_text=page_text[:5000],
    )


def _dedupe(events: list[Event]) -> list[Event]:
    seen: set[tuple[str, str]] = set()
    result: list[Event] = []
    for event in events:
        key = (event.title.lower().strip(), event.start.isoformat() if event.start else "")
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return result


def extract_events(html: str, url: str) -> list[Event]:
    soup = BeautifulSoup(html, "html.parser")
    page_text = _SPACE_RE.sub(" ", soup.get_text(" ", strip=True))

    events: list[Event] = []
    for data in _iter_jsonld(soup):
        for node in _walk(data):
            if not _is_event_node(node):
                continue
            event = _node_to_event(node, url, page_text)
            if event:
                events.append(event)

    if not events:
        fallback = _fallback_event(soup, url, page_text)
        if fallback:
            events.append(fallback)

    return _dedupe(events)
