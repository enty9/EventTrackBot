from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from .formatting import format_caption, format_details
from .models import Event

log = logging.getLogger(__name__)


async def send_event(bot: Bot, chat_id: int, event: Event) -> None:
    caption = format_caption(event)
    details = format_details(event)

    if event.image:
        try:
            await bot.send_photo(
                chat_id=chat_id,
                photo=event.image,
                caption=caption,
                disable_notification=False,
            )
            await bot.send_message(chat_id, details, disable_web_page_preview=True)
            return
        except TelegramRetryAfter as exc:
            await _sleep_retry(exc)
            try:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=event.image,
                    caption=caption,
                    disable_notification=False,
                )
                await bot.send_message(chat_id, details, disable_web_page_preview=True)
                return
            except TelegramBadRequest:
                pass
        except TelegramBadRequest:
            log.debug("Не удалось отправить постер %s", event.image)

    text = f"{caption}\n\n{details}"
    try:
        await bot.send_message(chat_id, text, disable_web_page_preview=True)
    except TelegramRetryAfter as exc:
        await _sleep_retry(exc)
        await bot.send_message(chat_id, text, disable_web_page_preview=True)


async def _sleep_retry(exc: TelegramRetryAfter) -> None:
    import asyncio

    await asyncio.sleep(exc.retry_after)


def is_forbidden_error(exc: BaseException) -> bool:
    return isinstance(exc, TelegramForbiddenError)
