from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str
    data_file: Path
    interval_seconds: int
    max_events_per_cycle: int
    search_results_per_query: int
    search_max_urls: int
    search_max_events: int
    user_agent: str


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, value)


def load_config() -> Config:
    load_dotenv(PROJECT_ROOT / ".env")

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "BOT_TOKEN не задан. Скопируй .env.example в .env и вставь токен от @BotFather."
        )

    interval_minutes = _env_int("SEARCH_INTERVAL_MINUTES", 20, minimum=5)
    data_file = Path(os.getenv("DATA_FILE", str(PROJECT_ROOT / "data" / "users.json")))

    return Config(
        bot_token=token,
        data_file=data_file,
        interval_seconds=interval_minutes * 60,
        max_events_per_cycle=_env_int("MAX_EVENTS_PER_CYCLE", 6),
        search_results_per_query=_env_int("SEARCH_RESULTS_PER_QUERY", 10),
        search_max_urls=_env_int("SEARCH_MAX_URLS", 30),
        search_max_events=_env_int("SEARCH_MAX_EVENTS", 50),
        user_agent=os.getenv("USER_AGENT", DEFAULT_USER_AGENT).strip() or DEFAULT_USER_AGENT,
    )
