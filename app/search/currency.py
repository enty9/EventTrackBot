from __future__ import annotations

import asyncio
import logging
import time

import httpx

from ..money import normalize_currency

log = logging.getLogger(__name__)

CBR_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
CACHE_SECONDS = 12 * 60 * 60
RETRY_SECONDS = 10 * 60


class CurrencyConverter:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._rates: dict[str, float] = {"RUB": 1.0}
        self._loaded_at = 0.0
        self._attempted_at = 0.0
        self._lock = asyncio.Lock()

    async def _ensure_rates(self) -> None:
        now = time.monotonic()
        if self._rates != {"RUB": 1.0} and now - self._loaded_at < CACHE_SECONDS:
            return
        if now - self._attempted_at < RETRY_SECONDS and self._attempted_at:
            return

        async with self._lock:
            now = time.monotonic()
            if self._rates != {"RUB": 1.0} and now - self._loaded_at < CACHE_SECONDS:
                return
            if now - self._attempted_at < RETRY_SECONDS and self._attempted_at:
                return
            self._attempted_at = now

            try:
                response = await self._client.get(CBR_URL, timeout=10.0)
                response.raise_for_status()
                payload = response.json()
                rates: dict[str, float] = {"RUB": 1.0}
                for code, info in (payload.get("Valute") or {}).items():
                    try:
                        nominal = float(info.get("Nominal") or 1)
                        value = float(info["Value"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if nominal > 0:
                        rates[str(code).upper()] = value / nominal
                if len(rates) > 1:
                    self._rates = rates
                    self._loaded_at = now
            except (httpx.HTTPError, ValueError, TypeError) as exc:
                log.info("Не удалось загрузить курсы ЦБ: %s", exc)

    async def to_rub(self, amount: float, currency: str) -> float | None:
        code = normalize_currency(currency)
        if not code or code == "RUB":
            return amount
        await self._ensure_rates()
        rate = self._rates.get(code)
        if not rate:
            return None
        return amount * rate
