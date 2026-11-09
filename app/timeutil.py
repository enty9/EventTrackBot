from __future__ import annotations

import re
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

MOSCOW = ZoneInfo("Europe/Moscow")

MONTHS = [
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]
MONTHS_INDEX = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "ма": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
}
WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NUMERIC_DATE_RE = re.compile(
    r"(?<!\d)(\d{1,2})\s*[./\-]\s*(\d{1,2})\s*[./\-]\s*(\d{2,4})(?!\d)"
)
_TEXT_DATE_RE = re.compile(
    r"(?<!\d)(\d{1,2})\s+(январ[яь]|феврал[яь]|марта?|апрел[яь]|ма[яй]|"
    r"июн[яь]|июл[яь]|августа?|сентябр[яь]|октябр[яь]|ноябр[яь]|декабр[яь])"
    r"(?:\s+(\d{4}))?",
    re.IGNORECASE,
)
_ISO_IN_TEXT_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    text = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", text)

    if _ISO_DATE_RE.fullmatch(text):
        try:
            return datetime.combine(date.fromisoformat(text), time.min)
        except ValueError:
            return None

    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass

    for fmt in (
        "%d.%m.%Y %H:%M",
        "%d.%m.%Y",
        "%d.%m.%y",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def parse_date_text(text: str, default_year: int | None = None) -> datetime | None:
    if not text:
        return None

    iso = _ISO_IN_TEXT_RE.search(text)
    if iso:
        try:
            return datetime.combine(
                date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3))),
                time.min,
            )
        except ValueError:
            pass

    numeric = _NUMERIC_DATE_RE.search(text)
    if numeric:
        day, month, year = (int(part) for part in numeric.groups())
        if year < 100:
            year += 2000
        try:
            return datetime.combine(date(year, month, day), time.min)
        except ValueError:
            pass

    word = _TEXT_DATE_RE.search(text)
    if word:
        day = int(word.group(1))
        month_name = word.group(2).lower()
        month = None
        for prefix, number in MONTHS_INDEX.items():
            if month_name.startswith(prefix):
                month = number
                break
        if month:
            year = int(word.group(3)) if word.group(3) else (default_year or date.today().year)
            try:
                return datetime.combine(date(year, month, day), time.min)
            except ValueError:
                pass
    return None


def to_moscow(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=MOSCOW)
    return value.astimezone(MOSCOW)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=MOSCOW)
    return value.astimezone(timezone.utc)


def format_event_date(start: datetime | None, end: datetime | None = None) -> str:
    if not start:
        return "Дата не указана"
    first = to_moscow(start)
    result = f"{WEEKDAYS[first.weekday()]}, {first.day} {MONTHS[first.month - 1]} {first.year}"
    if first.hour or first.minute:
        result += f", {first:%H:%M}"

    if end:
        last = to_moscow(end)
        if last.date() != first.date():
            result += f" — {last.day} {MONTHS[last.month - 1]} {last.year}"
            if last.hour or last.minute:
                result += f", {last:%H:%M}"
        elif last.hour or last.minute:
            result += f"–{last:%H:%M}"
    return result
