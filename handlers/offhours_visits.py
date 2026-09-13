"""Telegram flow for employee off-hours venue bookings."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from html import escape
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from application.offhours_visit_service import (
    MAX_EMPLOYEES_PER_VENUE_DAY,
    OffhoursVisitService,
    VENUES,
    local_today,
    week_visit_dates,
)
from config import GROUPS_WITH_OFFHOURS_VISITS, USERS_FILE
from data_models import user_name
from roles import get_user_group
from states import OFFHOURS_VISITS_MENU
from storage import load_json

WEEKDAY_LABELS = {
    3: "Четверг",
    4: "Пятница",
    5: "Суббота",
    6: "Воскресенье",
}


def offhours_home_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Bla Bla Bar", callback_data="offh_venue:bla_bla_bar")],
            [InlineKeyboardButton("Куранты", callback_data="offh_venue:kuranty")],
            [InlineKeyboardButton("Мои брони", callback_data="offh_my")],
        ]
    )


def _back_markup(target: str = "offh_home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=target)]])


def _date_label(value: str) -> str:
    parsed = date.fromisoformat(value)
    return f"{WEEKDAY_LABELS[parsed.weekday()]}, {parsed.strftime('%d.%m.%Y')}"


def _venue_day_records(bookings: list[dict[str, Any]], venue: str, day: date) -> list[dict[str, Any]]:
    iso_day = day.isoformat()
    return [item for item in bookings if item.get("venue") == venue and item.get("visit_date") == iso_day]


def venue_dates_markup(venue: str, bookings: list[dict[str, Any]], today: date | None = None) -> InlineKeyboardMarkup:
    current = today or local_today()
    keyboard: list[list[InlineKeyboardButton]] = []
    for day in week_visit_dates(current):
        occupied = len(_venue_day_records(bookings, venue, day))
        free = max(0, MAX_EMPLOYEES_PER_VENUE_DAY - occupied)
        prefix = WEEKDAY_LABELS[day.weekday()][:2]
        if day < current:
            label = f"{prefix}, {day.strftime('%d.%m')} — прошёл"
            callback = "offh_noop"
        elif free == 0:
            label = f"{prefix}, {day.strftime('%d.%m')} — мест нет"
            callback = f"offh_full:{venue}:{day.isoformat()}"
        else:
            label = f"{prefix}, {day.strftime('%d.%m')} — свободно {free} из 2"
            callback = f"offh_book:{venue}:{day.isoformat()}"
        keyboard.append([InlineKeyboardButton(label, callback_data=callback)])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="offh_home")])
    return InlineKeyboardMarkup(keyboard)


def my_bookings_markup(has_bookings: bool) -> InlineKeyboardMarkup:
    cancel_callback = "offh_cancel_menu" if has_bookings else "offh_no_bookings"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("❌ Отменить запись", callback_data=cancel_callback)],
            [InlineKeyboardButton("📋 Расписание недели", callback_data="offh_schedule")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="offh_home")],
        ]
    )


def _booking_line(record: dict[str, Any]) -> str:
    venue_name = VENUES.get(str(record.get("venue")), str(record.get("venue", "—")))
    visit_date = str(record.get("visit_date", ""))
    return f"• <b>{escape(venue_name)}</b> — {_date_label(visit_date)}"


async def _employee_identity(update: Update) -> tuple[str, str, str] | None:
    user_id = str(update.effective_user.id)
    group = await get_user_group(user_id)
    if group not in GROUPS_WITH_OFFHOURS_VISITS:
        return None
    users = await load_json(USERS_FILE)
    name = user_name(users.get(user_id), update.effective_user.full_name or user_id)
    if not name:
        return None
    return user_id, name, group


async def open_offhours_visits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    identity = await _employee_identity(update)
    if identity is None:
        await update.message.reply_text("⛔️ Внерабочие посещения доступны только сотрудникам A LAMP и R LAMP.")
        return ConversationHandler.END
    await update.message.reply_text(
        "🏪 <b>Внерабочие посещения</b>\n\nВыберите заведение или откройте свои брони:",
        reply_markup=offhours_home_markup(),
        parse_mode="HTML",
    )
    return OFFHOURS_VISITS_MENU


async def _render_home(query) -> None:
    await query.message.edit_text(
        "🏪 <b>Внерабочие посещения</b>\n\nВыберите заведение или откройте свои брони:",
        reply_markup=offhours_home_markup(),
        parse_mode="HTML",
    )


async def _render_venue(query, venue: str) -> None:
    service = OffhoursVisitService.from_default_storage()
    bookings = await service.active_bookings()
    await query.message.edit_text(
        f"🏪 <b>{escape(VENUES[venue])}</b>\n\nВыберите день. На одно заведение в один день могут записаться не более двух сотрудников:",
        reply_markup=venue_dates_markup(venue, bookings),
        parse_mode="HTML",
    )


async def _render_my_bookings(query, user_id: str) -> None:
    bookings = await OffhoursVisitService.from_default_storage().user_bookings(user_id)
    if bookings:
        body = "\n".join(_booking_line(record) for record in bookings)
        text = f"👤 <b>Мои брони</b>\n\n{body}"
    else:
        text = "👤 <b>Мои брони</b>\n\nАктивных броней нет."
    await query.message.edit_text(
        text,
        reply_markup=my_bookings_markup(bool(bookings)),
        parse_mode="HTML",
    )


async def _render_schedule(query) -> None:
    bookings = await OffhoursVisitService.from_default_storage().active_bookings()
    lines = ["📋 <b>Расписание недели</b>"]
    for day in week_visit_dates():
        lines.append(f"\n<b>{_date_label(day.isoformat())}</b>")
        for venue, venue_name in VENUES.items():
            records = _venue_day_records(bookings, venue, day)
            names = ", ".join(escape(str(record.get("name", "—"))) for record in records) or "свободно"
            lines.append(f"{escape(venue_name)}: {names} ({len(records)}/2)")
    await query.message.edit_text(
        "\n".join(lines),
        reply_markup=_back_markup("offh_my"),
        parse_mode="HTML",
    )


async def offhours_visit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    identity = await _employee_identity(update)
    if identity is None:
        await query.answer("Раздел доступен только сотрудникам A LAMP и R LAMP.", show_alert=True)
        await query.message.edit_text("⛔️ Раздел доступен только сотрудникам A LAMP и R LAMP.")
        return ConversationHandler.END
    user_id, name, group = identity
    data = str(query.data or "")

    if data == "offh_home":
        await query.answer()
        await _render_home(query)
        return OFFHOURS_VISITS_MENU
    if data == "offh_my":
        await query.answer()
        await _render_my_bookings(query, user_id)
        return OFFHOURS_VISITS_MENU
    if data == "offh_schedule":
        await query.answer()
        await _render_schedule(query)
        return OFFHOURS_VISITS_MENU
    if data == "offh_noop":
        await query.answer("Этот день уже прошёл.", show_alert=True)
        return OFFHOURS_VISITS_MENU
    if data == "offh_no_bookings":
        await query.answer("У вас нет активных броней для отмены.", show_alert=True)
        return OFFHOURS_VISITS_MENU

    if data.startswith("offh_venue:"):
        venue = data.split(":", 1)[1]
        if venue not in VENUES:
            await query.answer("Неизвестное заведение.", show_alert=True)
            return OFFHOURS_VISITS_MENU
        await query.answer()
        await _render_venue(query, venue)
        return OFFHOURS_VISITS_MENU

    if data.startswith("offh_full:"):
        await query.answer("На этот день уже записаны два сотрудника.", show_alert=True)
        return OFFHOURS_VISITS_MENU

    if data.startswith("offh_book:"):
        _, venue, visit_date = data.split(":", 2)
        if venue not in VENUES:
            await query.answer("Неизвестное заведение.", show_alert=True)
            return OFFHOURS_VISITS_MENU
        await query.answer()
        await query.message.edit_text(
            "🔎 <b>Подтвердите бронь</b>\n\n"
            f"Заведение: <b>{escape(VENUES[venue])}</b>\n"
            f"Дата: <b>{_date_label(visit_date)}</b>\n\n"
            "В этот день сотрудник может забронировать только одно заведение.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("✅ Забронировать", callback_data=f"offh_confirm:{venue}:{visit_date}")],
                    [InlineKeyboardButton("⬅️ Назад", callback_data=f"offh_venue:{venue}")],
                ]
            ),
            parse_mode="HTML",
        )
        return OFFHOURS_VISITS_MENU

    if data.startswith("offh_confirm:"):
        _, venue, visit_date = data.split(":", 2)
        result = await OffhoursVisitService.from_default_storage().book(user_id, name, group, venue, visit_date)
        if result.ok:
            await query.answer("Бронь создана.")
            await query.message.edit_text(
                "✅ <b>Бронь создана</b>\n\n"
                f"Заведение: <b>{escape(VENUES[venue])}</b>\n"
                f"Дата: <b>{_date_label(visit_date)}</b>\n"
                f"Место: <b>{result.details['occupied']} из 2</b>",
                reply_markup=my_bookings_markup(True),
                parse_mode="HTML",
            )
        elif result.code == "user_day_conflict":
            existing_name = escape(str(result.details.get("venue_name", "другое заведение")))
            await query.answer(
                f"На эту дату у вас уже есть бронь: {existing_name}. Два заведения в один день бронировать нельзя.",
                show_alert=True,
            )
        elif result.code == "venue_full":
            await query.answer("Пока вы подтверждали, два места уже заняли. Выберите другой день.", show_alert=True)
            await _render_venue(query, venue)
        else:
            await query.answer("Не удалось создать бронь. Проверьте дату и попробуйте снова.", show_alert=True)
        return OFFHOURS_VISITS_MENU

    if data == "offh_cancel_menu":
        await query.answer()
        bookings = await OffhoursVisitService.from_default_storage().user_bookings(user_id)
        buttons = [
            [InlineKeyboardButton(f"❌ {VENUES.get(str(item.get('venue')), 'Заведение')} · {str(item.get('visit_date'))[5:]}", callback_data=f"offh_cancel:{item['booking_id']}")]
            for item in bookings
        ]
        buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="offh_my")])
        await query.message.edit_text(
            "❌ <b>Отмена брони</b>\n\nВыберите запись, которую нужно отменить:",
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="HTML",
        )
        return OFFHOURS_VISITS_MENU

    if data.startswith("offh_cancel:"):
        booking_id = data.split(":", 1)[1]
        result = await OffhoursVisitService.from_default_storage().cancel(user_id, booking_id)
        if result.ok:
            await query.answer("Бронь отменена.", show_alert=True)
        else:
            await query.answer("Бронь не найдена или уже отменена.", show_alert=True)
        await _render_my_bookings(query, user_id)
        return OFFHOURS_VISITS_MENU

    await query.answer()
    return OFFHOURS_VISITS_MENU


__all__ = [
    "my_bookings_markup",
    "offhours_home_markup",
    "offhours_visit_callback",
    "open_offhours_visits",
    "venue_dates_markup",
]
