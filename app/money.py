from __future__ import annotations

import re

CURRENCY_MAP = {
    "rub": "RUB",
    "rur": "RUB",
    "ruble": "RUB",
    "rubles": "RUB",
    "₽": "RUB",
    "руб": "RUB",
    "руб.": "RUB",
    "рублей": "RUB",
    "рубля": "RUB",
    "usd": "USD",
    "$": "USD",
    "долл": "USD",
    "доллар": "USD",
    "долларов": "USD",
    "eur": "EUR",
    "€": "EUR",
    "евро": "EUR",
    "kzt": "KZT",
    "тенге": "KZT",
    "byn": "BYN",
    "бел": "BYN",
    "uah": "UAH",
    "гривн": "UAH",
    "gbp": "GBP",
    "£": "GBP",
}

SYMBOLS = {
    "RUB": "₽",
    "USD": "$",
    "EUR": "€",
    "KZT": "₸",
    "BYN": "Br",
    "UAH": "₴",
    "GBP": "£",
}

_PRICE_RE = re.compile(r"\d+(?:[.,]\d+)?")


def normalize_currency(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    if not text:
        return ""
    if text in CURRENCY_MAP:
        return CURRENCY_MAP[text]
    for key, code in CURRENCY_MAP.items():
        if key and key in text:
            return code
    return text.upper()


def parse_price(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower().replace("\xa0", " ")
    if not text:
        return None
    if text in {"free", "бесплатно", "free admission", "вход свободный"}:
        return 0.0
    match = _PRICE_RE.search(text.replace(" ", ""))
    if not match:
        return None
    try:
        return float(match.group(0).replace(",", "."))
    except ValueError:
        return None


def format_money(amount: float) -> str:
    if amount is None:
        return ""
    if abs(amount - round(amount)) < 0.01:
        return f"{round(amount):,}".replace(",", " ")
    return f"{amount:,.2f}".replace(",", " ").replace(".", ",")
