from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .cities import POPULAR_CITIES
from .spheres import SPHERES


def cities_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for index, city in enumerate(POPULAR_CITIES):
        row.append(InlineKeyboardButton(text=city, callback_data=f"city:{index}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [InlineKeyboardButton(text="✍️ Ввести другой город", callback_data="city_custom")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def controls_keyboard(running: bool) -> InlineKeyboardMarkup:
    if running:
        rows = [
            [InlineKeyboardButton(text="⏹ Остановить поиск", callback_data="stop")],
            [InlineKeyboardButton(text="🏙 Сменить город", callback_data="change_city")],
            [InlineKeyboardButton(text="🎯 Сменить сферу", callback_data="change_sphere")],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text="🔎 Найти мероприятия", callback_data="search")],
            [InlineKeyboardButton(text="🏙 Сменить город", callback_data="change_city")],
            [InlineKeyboardButton(text="🎯 Сменить сферу", callback_data="change_sphere")],
        ]
    rows.append(
        [
            InlineKeyboardButton(
                text="🎉 Все мероприятия города", callback_data="search_all"
            )
        ]
    )
    rows.append([InlineKeyboardButton(text="ℹ️ Статус", callback_data="status")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def spheres_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for sphere in SPHERES:
        row.append(
            InlineKeyboardButton(
                text=f"{sphere.emoji} {sphere.title}",
                callback_data=f"sphere:{sphere.key}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_city_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, искать здесь", callback_data="city_confirm"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Изменить город", callback_data="city_cancel"
                )
            ],
        ]
    )
