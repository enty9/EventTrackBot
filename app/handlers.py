from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .cities import (
    POPULAR_CITIES,
    is_known_city,
    is_valid_city_name,
    normalize_city,
)
from .config import Config
from .keyboards import (
    cities_keyboard,
    confirm_city_keyboard,
    controls_keyboard,
    spheres_keyboard,
)
from .manager import MonitorManager
from .spheres import ALL_SPHERE, SPHERES_BY_KEY, sphere_title
from .storage import Storage

log = logging.getLogger(__name__)
router = Router(name="main")


class CityStates(StatesGroup):
    waiting_city = State()


def _esc(value: str | None) -> str:
    return html.escape(value or "", quote=False)


def _menu_text(
    city: str, sphere: str | None, running: bool, interval_minutes: int
) -> str:
    if running:
        status = (
            "🔎 <b>Поиск запущен.</b>\n"
            f"Бот проверяет интернет каждые {interval_minutes} мин. "
            "Нажми «⏹ Остановить поиск», чтобы остановиться."
        )
    else:
        status = (
            "Нажми «🔎 Найти мероприятия», и бот начнёт постоянно искать "
            "события в выбранной сфере."
        )
    return (
        f"🏙 Город: <b>{_esc(city)}</b>\n"
        f"🎯 Сфера: <b>{_esc(sphere_title(sphere))}</b>\n\n{status}"
    )


async def _prompt_sphere(message: Message) -> None:
    await message.answer(
        "🎯 <b>Выбери сферу мероприятий</b>\n\n"
        "Можно искать IT, шахматы, аниме или все мероприятия города.",
        reply_markup=spheres_keyboard(),
    )


async def _edit_sphere_prompt(callback: CallbackQuery) -> None:
    await _edit_message(
        callback,
        "🎯 <b>Выбери сферу мероприятий</b>\n\n"
        "Можно искать IT, шахматы, аниме или все мероприятия города.",
        spheres_keyboard(),
    )


async def _prompt_city(message: Message, state: FSMContext) -> None:
    await state.set_state(CityStates.waiting_city)
    await state.update_data(pending_city=None)
    await message.answer(
        "🏙 <b>Выбери город России</b>\n\n"
        "Можно нажать на популярный город или ввести свой.",
        reply_markup=cities_keyboard(),
    )


async def _apply_city(
    user_id: int,
    city: str,
    state: FSMContext,
    storage: Storage,
    manager: MonitorManager,
) -> None:
    await state.clear()
    record = await storage.get(user_id)
    if record.running and record.city != city:
        await manager.stop(user_id)
    await storage.update(user_id, city=city)


async def _edit_message(
    callback: CallbackQuery, text: str, markup=None
) -> None:
    if callback.message is None:
        await callback.answer()
        return
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=markup)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, storage: Storage, config: Config) -> None:
    user = message.from_user
    if user is None:
        return
    await state.clear()
    record = await storage.get(user.id)
    if not record.city:
        await _prompt_city(message, state)
    elif not record.sphere:
        await _prompt_sphere(message)
    else:
        await message.answer(
            _menu_text(
                record.city, record.sphere, record.running, config.interval_seconds // 60
            ),
            reply_markup=controls_keyboard(record.running),
        )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "ℹ️ <b>Как пользоваться</b>\n\n"
        "1. Выбери город России.\n"
        "2. Выбери сферу: IT, шахматы, аниме или «Все мероприятия».\n"
        "3. Нажми «🔎 Найти мероприятия» — бот начнёт постоянно искать "
        "события в выбранной сфере (или все события города) и присылать новые.\n"
        "4. Нажми «⏹ Остановить поиск», чтобы остановиться. После этого "
        "можно сменить город или сферу и снова запустить поиск.\n\n"
        "Команда /all или кнопка «🎉 Все мероприятия города» сразу запускает "
        "поиск всех мероприятий в выбранном городе.\n\n"
        "В карточке есть дата, место, постер, описание, ограничения, "
        "источник и ссылка для регистрации. Если вход платный, будет "
        "показан значок 💵 и цена в рублях.\n\n"
        "Команды: /start, /city, /sphere, /all, /stop, /status, /help"
    )


@router.message(Command("city"))
async def cmd_city(
    message: Message,
    state: FSMContext,
    storage: Storage,
    manager: MonitorManager,
) -> None:
    user = message.from_user
    if user is None:
        return
    record = await storage.get(user.id)
    if record.running:
        await manager.stop(user.id)
        await message.answer("⏹ Поиск остановлен. Теперь можно выбрать другой город.")
    await _prompt_city(message, state)


@router.message(Command("sphere"))
async def cmd_sphere(
    message: Message,
    storage: Storage,
    manager: MonitorManager,
) -> None:
    user = message.from_user
    if user is None:
        return
    record = await storage.get(user.id)
    if record.running:
        await manager.stop(user.id)
        await message.answer("⏹ Поиск остановлен. Теперь можно выбрать другую сферу.")
    await _prompt_sphere(message)


@router.message(Command("all"))
async def cmd_all(
    message: Message,
    state: FSMContext,
    storage: Storage,
    manager: MonitorManager,
    config: Config,
) -> None:
    user = message.from_user
    if user is None:
        return
    record = await storage.get(user.id)
    if not record.city:
        await message.answer("Сначала выбери город, а затем повтори /all.")
        await _prompt_city(message, state)
        return
    await manager.start(user.id, record.city, ALL_SPHERE)
    record = await storage.get(user.id)
    await message.answer(
        _menu_text(
            record.city or "",
            ALL_SPHERE,
            True,
            config.interval_seconds // 60,
        )
        + "\n\nПервые результаты пришлю после проверки источников (обычно до минуты).",
        reply_markup=controls_keyboard(True),
    )


@router.message(Command("stop"))
async def cmd_stop(
    message: Message,
    storage: Storage,
    manager: MonitorManager,
    config: Config,
) -> None:
    user = message.from_user
    if user is None:
        return
    await manager.stop(user.id)
    record = await storage.get(user.id)
    if record.city:
        await message.answer(
            _menu_text(
                record.city, record.sphere, False, config.interval_seconds // 60
            ),
            reply_markup=controls_keyboard(False),
        )
    else:
        await message.answer("Поиск остановлен. Сначала выбери город: /city")


@router.message(Command("status"))
async def cmd_status(
    message: Message,
    storage: Storage,
    config: Config,
) -> None:
    user = message.from_user
    if user is None:
        return
    record = await storage.get(user.id)
    status = "🔎 работает" if record.running else "⏹ остановлен"
    city = record.city or "не выбран"
    sphere = sphere_title(record.sphere) if record.sphere else "не выбрана"
    await message.answer(
        f"🏙 Город: <b>{_esc(city)}</b>\n"
        f"🎯 Сфера: <b>{_esc(sphere)}</b>\n"
        f"Статус: {status}\n"
        f"Интервал проверки: {config.interval_seconds // 60} мин."
    )


@router.callback_query(F.data.startswith("city:"))
async def city_selected(
    callback: CallbackQuery,
    state: FSMContext,
    storage: Storage,
    manager: MonitorManager,
    config: Config,
) -> None:
    user = callback.from_user
    if user is None or callback.data is None:
        return
    try:
        index = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("Не удалось выбрать город", show_alert=True)
        return
    if not 0 <= index < len(POPULAR_CITIES):
        await callback.answer("Неизвестный город", show_alert=True)
        return

    city = POPULAR_CITIES[index]
    await _apply_city(user.id, city, state, storage, manager)
    record = await storage.get(user.id)
    await callback.answer()
    if not record.sphere:
        await _edit_sphere_prompt(callback)
        return
    await _edit_message(
        callback,
        _menu_text(
            record.city or city,
            record.sphere,
            record.running,
            config.interval_seconds // 60,
        ),
        controls_keyboard(record.running),
    )


@router.callback_query(F.data == "city_custom")
async def city_custom(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CityStates.waiting_city)
    await state.update_data(pending_city=None)
    await callback.answer()
    await _edit_message(
        callback,
        "✍️ <b>Напиши название города России</b>\n\n"
        "Например: Москва, Казань, Нижний Новгород.",
        cities_keyboard(),
    )


@router.callback_query(F.data == "city_confirm")
async def city_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    storage: Storage,
    manager: MonitorManager,
    config: Config,
) -> None:
    user = callback.from_user
    if user is None:
        return
    data = await state.get_data()
    city = data.get("pending_city")
    if not city:
        await callback.answer("Город не найден, введи его ещё раз", show_alert=True)
        return
    await _apply_city(user.id, city, state, storage, manager)
    record = await storage.get(user.id)
    await callback.answer()
    if not record.sphere:
        await _edit_sphere_prompt(callback)
        return
    await _edit_message(
        callback,
        _menu_text(
            record.city or city,
            record.sphere,
            record.running,
            config.interval_seconds // 60,
        ),
        controls_keyboard(record.running),
    )


@router.callback_query(F.data == "city_cancel")
async def city_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(pending_city=None)
    await callback.answer()
    await _edit_message(
        callback,
        "🏙 <b>Выбери город России</b>\n\n"
        "Можно нажать на популярный город или ввести свой.",
        cities_keyboard(),
    )


@router.callback_query(F.data == "search")
async def start_search(
    callback: CallbackQuery,
    state: FSMContext,
    storage: Storage,
    manager: MonitorManager,
    config: Config,
) -> None:
    user = callback.from_user
    if user is None:
        return
    record = await storage.get(user.id)
    if not record.city:
        await callback.answer("Сначала выбери город", show_alert=True)
        if callback.message:
            await _prompt_city(callback.message, state)
        return
    if not record.sphere:
        await callback.answer("Сначала выбери сферу", show_alert=True)
        await _edit_sphere_prompt(callback)
        return
    if record.running:
        await callback.answer("Поиск уже запущен")
        return

    await manager.start(user.id, record.city, record.sphere)
    await callback.answer("Поиск запущен")
    await _edit_message(
        callback,
        _menu_text(record.city, record.sphere, True, config.interval_seconds // 60)
        + "\n\nПервые результаты пришлю после проверки источников (обычно до минуты).",
        controls_keyboard(True),
    )


@router.callback_query(F.data == "search_all")
async def start_search_all(
    callback: CallbackQuery,
    state: FSMContext,
    storage: Storage,
    manager: MonitorManager,
    config: Config,
) -> None:
    user = callback.from_user
    if user is None:
        return
    record = await storage.get(user.id)
    if not record.city:
        await callback.answer("Сначала выбери город", show_alert=True)
        if callback.message:
            await _prompt_city(callback.message, state)
        return

    await manager.start(user.id, record.city, ALL_SPHERE)
    await callback.answer("Ищу все мероприятия города")
    await _edit_message(
        callback,
        _menu_text(
            record.city, ALL_SPHERE, True, config.interval_seconds // 60
        )
        + "\n\nПервые результаты пришлю после проверки источников (обычно до минуты).",
        controls_keyboard(True),
    )


@router.callback_query(F.data == "stop")
async def stop_search(
    callback: CallbackQuery,
    storage: Storage,
    manager: MonitorManager,
    config: Config,
) -> None:
    user = callback.from_user
    if user is None:
        return
    await manager.stop(user.id)
    record = await storage.get(user.id)
    await callback.answer("Поиск остановлен")
    await _edit_message(
        callback,
        _menu_text(
            record.city or "не выбран",
            record.sphere,
            False,
            config.interval_seconds // 60,
        ),
        controls_keyboard(False),
    )


@router.callback_query(F.data == "change_city")
async def change_city(
    callback: CallbackQuery,
    state: FSMContext,
    storage: Storage,
    manager: MonitorManager,
) -> None:
    user = callback.from_user
    if user is None:
        return
    record = await storage.get(user.id)
    if record.running:
        await manager.stop(user.id)
    await state.set_state(CityStates.waiting_city)
    await state.update_data(pending_city=None)
    await callback.answer()
    await _edit_message(
        callback,
        "🏙 <b>Выбери новый город России</b>\n\n"
        "Можно нажать на популярный город или ввести свой.",
        cities_keyboard(),
    )


@router.callback_query(F.data == "change_sphere")
async def change_sphere(
    callback: CallbackQuery,
    storage: Storage,
    manager: MonitorManager,
) -> None:
    user = callback.from_user
    if user is None:
        return
    record = await storage.get(user.id)
    if record.running:
        await manager.stop(user.id)
    await callback.answer()
    await _edit_message(
        callback,
        "🎯 <b>Выбери новую сферу мероприятий</b>\n\n"
        "Можно искать IT, шахматы, аниме или все мероприятия города.",
        spheres_keyboard(),
    )


@router.callback_query(F.data.startswith("sphere:"))
async def sphere_selected(
    callback: CallbackQuery,
    storage: Storage,
    manager: MonitorManager,
    config: Config,
) -> None:
    user = callback.from_user
    if user is None or callback.data is None:
        return
    key = callback.data.split(":", 1)[1]
    if key not in SPHERES_BY_KEY:
        await callback.answer("Неизвестная сфера", show_alert=True)
        return

    record = await storage.get(user.id)
    if record.running and record.sphere != key:
        await manager.stop(user.id)
    await storage.update(user.id, sphere=key)
    record = await storage.get(user.id)
    await callback.answer()

    if not record.city:
        await _edit_message(
            callback,
            "🏙 <b>Выбери город России</b>\n\n"
            "Можно нажать на популярный город или ввести свой.",
            cities_keyboard(),
        )
        return

    await _edit_message(
        callback,
        _menu_text(
            record.city, key, record.running, config.interval_seconds // 60
        ),
        controls_keyboard(record.running),
    )


@router.callback_query(F.data == "status")
async def status_callback(callback: CallbackQuery, storage: Storage) -> None:
    user = callback.from_user
    if user is None:
        return
    record = await storage.get(user.id)
    status = "🔎 Работает" if record.running else "⏹ Остановлен"
    city = record.city or "не выбран"
    sphere = sphere_title(record.sphere) if record.sphere else "не выбрана"
    await callback.answer(
        f"{status}\nГород: {city}\nСфера: {sphere}", show_alert=True
    )


@router.message(CityStates.waiting_city, F.text)
async def city_text(
    message: Message,
    state: FSMContext,
    storage: Storage,
    manager: MonitorManager,
    config: Config,
) -> None:
    user = message.from_user
    if user is None:
        return
    raw = (message.text or "").strip()
    if raw.lower() in {"отмена", "cancel", "/cancel"}:
        await state.clear()
        await message.answer("Выбор города отменён.", reply_markup=controls_keyboard(False))
        return

    if not is_valid_city_name(raw):
        await message.answer(
            "Не похоже на название города. Напиши только название, например: "
            "«Москва» или «Нижний Новгород»."
        )
        return

    city = normalize_city(raw)
    if is_known_city(city):
        await _apply_city(user.id, city, state, storage, manager)
        record = await storage.get(user.id)
        if not record.sphere:
            await _prompt_sphere(message)
            return
        await message.answer(
            _menu_text(
                record.city or city,
                record.sphere,
                record.running,
                config.interval_seconds // 60,
            ),
            reply_markup=controls_keyboard(record.running),
        )
        return

    await state.update_data(pending_city=city)
    await message.answer(
        f"Я не нашёл «{_esc(city)}» в списке городов. Всё равно искать там?\n\n"
        "Если это город России, нажми «✅ Да».",
        reply_markup=confirm_city_keyboard(),
    )


@router.message(F.text & ~F.text.startswith("/"))
async def fallback_text(message: Message, storage: Storage, config: Config) -> None:
    user = message.from_user
    if user is None:
        return
    record = await storage.get(user.id)
    if record.city:
        await message.answer(
            "Пользуйся кнопками под сообщением. Чтобы сменить город — /city, "
            "сферу — /sphere",
            reply_markup=controls_keyboard(record.running),
        )
    else:
        await message.answer("Сначала выбери город командой /city")
