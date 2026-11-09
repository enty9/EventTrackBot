from __future__ import annotations

import html
import re

from .models import Event
from .money import SYMBOLS, format_money, normalize_currency
from .timeutil import format_event_date

_SPACE_RE = re.compile(r"\s+")


def _esc(value: str | None) -> str:
    if not value:
        return ""
    return html.escape(_SPACE_RE.sub(" ", str(value)).strip(), quote=False)


def _unique_parts(parts: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for part in parts:
        cleaned = _SPACE_RE.sub(" ", part or "").strip(" ,")
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def format_price(event: Event) -> str:
    if event.price is None or event.price <= 0:
        return ""

    if event.price_rub is not None and event.price_rub > 0:
        amount = event.price_rub
        symbol = "₽"
    else:
        code = normalize_currency(event.currency) or "RUB"
        amount = event.price
        symbol = SYMBOLS.get(code, code)

    prefix = "от " if event.price_from else ""
    return f"💵 {prefix}{format_money(amount)} {symbol}"


def event_location(event: Event) -> str:
    parts = _unique_parts([event.venue, event.city, event.address])
    return ", ".join(parts)


def format_caption(event: Event) -> str:
    lines = [f"🎯 <b>{_esc(event.title)}</b>", ""]
    lines.append(f"📅 {_esc(format_event_date(event.start, event.end))}")

    location = event_location(event)
    if location:
        lines.append(f"📍 {_esc(location)}")

    if event.attendance:
        lines.append(f"💻 {_esc(event.attendance)}")

    price = format_price(event)
    if price:
        lines.append(price)

    if event.source:
        lines.append(f"🔗 {_esc(event.source)}")

    return "\n".join(lines)


def format_details(event: Event) -> str:
    blocks: list[str] = []

    if event.description:
        blocks.append(f"📝 <b>Описание</b>\n{_esc(event.description[:1400])}")

    if event.organizer:
        blocks.append(f"👤 <b>Организатор</b>\n{_esc(event.organizer)}")

    details_url = event.official_url or event.url
    how_to_attend = [
        "🎟 <b>Как попасть</b>",
        f"Подробности, программа и регистрация: {_esc(details_url)}",
    ]
    if event.registration_url and event.registration_url not in {
        event.url,
        details_url,
    }:
        how_to_attend.append(f"Регистрация или билеты: {_esc(event.registration_url)}")
    blocks.append("\n".join(how_to_attend))

    if event.age:
        restrictions = f"Возрастное ограничение: {_esc(event.age)}"
    else:
        restrictions = "Ограничения не указаны."
    blocks.append(f"⚠️ <b>Ограничения</b>\n{restrictions}")

    blocks.append(f"🌐 <b>Источник</b>\n{_esc(event.url)}")

    return "\n\n".join(blocks)


def format_full_card(event: Event) -> str:
    return f"{format_caption(event)}\n\n{format_details(event)}"
