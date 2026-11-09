from __future__ import annotations

import asyncio
import html
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

from .search.engine import EventSearcher
from .sender import send_event
from .spheres import DEFAULT_SPHERE, sphere_title
from .storage import Storage

log = logging.getLogger(__name__)


class MonitorManager:
    def __init__(
        self,
        bot: Bot,
        storage: Storage,
        searcher: EventSearcher,
        *,
        interval_seconds: int,
        max_events_per_cycle: int,
    ) -> None:
        self._bot = bot
        self._storage = storage
        self._searcher = searcher
        self._interval = interval_seconds
        self._max_events = max_events_per_cycle
        self._tasks: dict[int, asyncio.Task] = {}

    async def start(
        self, user_id: int, city: str, sphere: str = DEFAULT_SPHERE
    ) -> None:
        await self._cancel(user_id)
        await self._storage.update(user_id, city=city, sphere=sphere, running=True)
        self._spawn(user_id, city, sphere, delay=0)

    async def stop(self, user_id: int) -> None:
        await self._cancel(user_id)
        await self._storage.update(user_id, running=False)

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def restore(self) -> None:
        users = await self._storage.all_users()
        started = 0
        for user_id, record in users:
            if record.running and record.city:
                sphere = record.sphere or DEFAULT_SPHERE
                if not record.sphere:
                    await self._storage.update(user_id, sphere=sphere)
                self._spawn(user_id, record.city, sphere, delay=5 + started * 3)
                started += 1
        if started:
            log.info("Возобновлён мониторинг для %d пользователей", started)

    def _spawn(
        self, user_id: int, city: str, sphere: str, *, delay: float
    ) -> None:
        task = asyncio.create_task(
            self._run(user_id, city, sphere, delay),
            name=f"monitor:{user_id}:{city}:{sphere}",
        )
        self._tasks[user_id] = task

    async def _cancel(self, user_id: int) -> None:
        task = self._tasks.pop(user_id, None)
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Ошибка при остановке мониторинга пользователя %s", user_id)

    async def _run(
        self, user_id: int, city: str, sphere: str, delay: float
    ) -> None:
        try:
            if delay:
                await asyncio.sleep(delay)
            first_cycle = True
            while True:
                record = await self._storage.get(user_id)
                if not record.running:
                    return
                await self._cycle(user_id, city, sphere, first_cycle)
                first_cycle = False
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Мониторинг пользователя %s остановлен из-за ошибки", user_id)
        finally:
            current = asyncio.current_task()
            if self._tasks.get(user_id) is current:
                self._tasks.pop(user_id, None)

    async def _cycle(
        self, user_id: int, city: str, sphere: str, first_cycle: bool
    ) -> None:
        try:
            events = await self._searcher.search(city, sphere)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Ошибка поиска для пользователя %s", user_id)
            if first_cycle:
                await self._safe_message(
                    user_id,
                    "⚠️ Не удалось выполнить поиск. Проверю ещё раз через "
                    f"{max(1, self._interval // 60)} мин.",
                )
            return

        record = await self._storage.get(user_id)
        fresh = [event for event in events if event.key not in record.seen]
        sent_keys: list[str] = []

        for event in fresh[: self._max_events]:
            if not record.running:
                return
            try:
                await send_event(self._bot, user_id, event)
            except TelegramForbiddenError:
                log.info("Пользователь %s заблокировал бота", user_id)
                await self._storage.update(user_id, running=False)
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Не удалось отправить мероприятие %s", event.url)
                continue
            sent_keys.append(event.key)

        if sent_keys:
            await self._storage.mark_seen(user_id, sent_keys)
        elif first_cycle:
            await self._safe_message(
                user_id,
                f"Пока новых мероприятий в городе <b>{html.escape(city)}</b> "
                f"по сфере <b>{html.escape(sphere_title(sphere))}</b> не найдено. "
                "Продолжаю проверять.",
            )

    async def _safe_message(self, user_id: int, text: str) -> None:
        try:
            await self._bot.send_message(user_id, text)
        except TelegramForbiddenError:
            await self._storage.update(user_id, running=False)
        except Exception:
            log.debug("Не удалось отправить служебное сообщение", exc_info=True)
