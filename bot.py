from __future__ import annotations

import asyncio
import logging

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import load_config
from app.handlers import router
from app.manager import MonitorManager
from app.search.engine import EventSearcher
from app.storage import Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger("eventtrackbot")


async def main() -> None:
    config = load_config()

    storage = Storage(config.data_file)
    await storage.load()

    headers = {
        "User-Agent": config.user_agent,
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
    }

    async with httpx.AsyncClient(
        headers=headers,
        timeout=httpx.Timeout(25.0, connect=15.0),
        follow_redirects=True,
    ) as client:
        searcher = EventSearcher(
            client,
            results_per_query=config.search_results_per_query,
            max_urls=config.search_max_urls,
            max_events=config.search_max_events,
        )
        bot = Bot(
            token=config.bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        manager = MonitorManager(
            bot,
            storage,
            searcher,
            interval_seconds=config.interval_seconds,
            max_events_per_cycle=config.max_events_per_cycle,
        )

        dispatcher = Dispatcher(storage=MemoryStorage())
        dispatcher["config"] = config
        dispatcher["storage"] = storage
        dispatcher["manager"] = manager
        dispatcher.include_router(router)

        async def on_startup() -> None:
            log.info("Бот запущен. Интервал поиска: %d мин.", config.interval_seconds // 60)
            await manager.restore()

        async def on_shutdown() -> None:
            log.info("Останавливаю мониторинг...")
            await manager.shutdown()

        dispatcher.startup.register(on_startup)
        dispatcher.shutdown.register(on_shutdown)

        try:
            await bot.delete_webhook(drop_pending_updates=False)
        except TelegramAPIError as exc:
            log.debug("Не удалось удалить webhook: %s", exc)

        try:
            await dispatcher.start_polling(bot, close_bot_session=False)
        finally:
            await manager.shutdown()
            await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit) as exc:
        if isinstance(exc, SystemExit) and exc.code:
            log.error("%s", exc)
