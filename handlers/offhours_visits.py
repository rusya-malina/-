"""Telegram flow for employee off-hours venue bookings."""

from __future__ import annotations

from datetime import date
from html import escape
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes, ConversationHandler

from application.offhours_visit_service import (
    MAX_EMPLOYEES_PER_VENUE_DAY,
    VENUES,
    OffhoursVisitService,
    local_today,
    month_visit_dates,
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
WEEKDAY_SHORT = {3: "Ч", 4: "П", 5: "С", 6: "В"}


def offhours_home_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Bla Bla Bar", callback_data="offh_venue:bla_bla_bar")],
            [InlineKeyboardButton("Куранты", callback_data="offh_venue:kuranty")],
            [InlineKeyboardButton("Сплетни", callback_data="offh_venue:spletni")],
            [InlineKeyboardButton("Зебра (Hype)", callback_data="offh_venue:zebra_hype")],
            [InlineKeyboardButton("Q bar", callback_data="offh_venue:q_bar")],
            [InlineKeyboardButton("John Dilinger", callback_data="offh_venue:john_dilinger")],
            [InlineKeyboardButton("Midnight", callback_data="offh_venue:midnight")],
            [InlineKeyboardButton("Зевон (суб)", callback_data="offh_venue:zevon")],
            [InlineKeyboardButton("Шанхай", callback_data="offh_venue:shanghai")],
            [InlineKeyboardButton("Гао Гао", callback_data="offh_venue:gao_gao")],
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
    date_buttons: list[InlineKeyboardButton] = []
    for day in month_visit_dates(current, venue):
        occupied = len(_venue_day_records(bookings, venue, day))
        marker = "·" if day < current else "✖" if occupied >= MAX_EMPLOYEES_PER_VENUE_DAY else ""
        label = f"{WEEKDAY_SHORT[day.weekday()]} {day.day:02d}{marker}"
        date_buttons.append(InlineKeyboardButton(label, callback_data=f"offh_day:{venue}:{day.isoformat()}"))
    keyboard = [date_buttons[index : index + 4] for index in range(0, len(date_buttons), 4)]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="offh_home")])
    return InlineKeyboardMarkup(keyboard)


def my_bookings_markup(has_bookings: bool) -> InlineKeyboardMarkup:
    cancel_callback = "offh_cancel_menu" if has_bookings else "offh_no_bookings"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("❌ Отменить запись", callback_data=cancel_callback)],
            [InlineKeyboardButton("📋 Расписание месяца", callback_data="offh_schedule")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="offh_home")],
        ]
    )


def coordinator_venues_markup() -> InlineKeyboardMarkup:
    """Return one compact venue selector for the management booking report."""
    buttons = [InlineKeyboardButton(name, callback_data=f"offh_report_venue:{venue}") for venue, name in VENUES.items()]
    keyboard = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="offh_report_close")])
    return InlineKeyboardMarkup(keyboard)


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
        f"🏪 <b>{escape(VENUES[venue])}</b>\n\nВыберите дату текущего месяца. Кнопки расположены по четыре в строке; «·» означает прошедшую дату, «✖» — два занятых места:",
        reply_markup=venue_dates_markup(venue, bookings),
        parse_mode="HTML",
    )


async def _render_day(query, venue: str, visit_date: str) -> None:
    try:
        selected_day = date.fromisoformat(visit_date)
    except ValueError:
        await query.message.edit_text("❌ Некорректная дата.", reply_markup=_back_markup(f"offh_venue:{venue}"))
        return
    bookings = await OffhoursVisitService.from_default_storage().active_bookings()
    records = _venue_day_records(bookings, venue, selected_day)
    if records:
        booked_names = "\n".join(f"• {escape(str(item.get('name', '—')))}" for item in records)
        occupancy = f"Уже забронировали:\n{booked_names}"
    else:
        occupancy = "Броней нет."

    buttons: list[list[InlineKeyboardButton]] = []
    current = local_today()
    if selected_day < current:
        status = "\n\nЭта дата уже прошла. Бронирование недоступно."
    elif selected_day.year != current.year or selected_day.month != current.month:
        status = "\n\nМожно бронировать только даты текущего месяца."
    elif len(records) >= MAX_EMPLOYEES_PER_VENUE_DAY:
        status = "\n\nВсе два места заняты."
    else:
        status = f"\n\nСвободно мест: {MAX_EMPLOYEES_PER_VENUE_DAY - len(records)} из 2."
        buttons.append([InlineKeyboardButton("✅ Забронировать", callback_data=f"offh_confirm:{venue}:{visit_date}")])
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"offh_venue:{venue}")])
    await query.message.edit_text(
        f"🏪 <b>{escape(VENUES[venue])}</b>\n📅 <b>{_date_label(visit_date)}</b>\n\n{occupancy}{status}",
        reply_markup=InlineKeyboardMarkup(buttons),
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
    current = local_today()
    lines = [f"📋 <b>Расписание за {current.strftime('%m.%Y')}</b>"]
    for day in month_visit_dates(current):
        lines.append(f"\n<b>{_date_label(day.isoformat())}</b>")
        for venue, venue_name in VENUES.items():
            if day not in month_visit_dates(current, venue):
                continue
            records = _venue_day_records(bookings, venue, day)
            names = ", ".join(escape(str(record.get("name", "—"))) for record in records) or "свободно"
            lines.append(f"{escape(venue_name)}: {names} ({len(records)}/2)")
    await query.message.edit_text(
        "\n".join(lines),
        reply_markup=_back_markup("offh_my"),
        parse_mode="HTML",
    )


async def _render_coordinator_report(query, venue: str) -> None:
    current = local_today()
    bookings = await OffhoursVisitService.from_default_storage().active_bookings()
    venue_name = escape(VENUES[venue])
    lines = [f"📋 <b>{venue_name}</b> — брони за {current.strftime('%m.%Y')}\n"]
    for day in month_visit_dates(current, venue):
        records = _venue_day_records(bookings, venue, day)
        names = [escape(str(record.get("name", "—"))) for record in records]
        if len(names) == 2:
            pair = f"{names[0]} + {names[1]}"
        elif len(names) == 1:
            pair = f"{names[0]} + —"
        else:
            pair = "—"
        lines.append(f"{WEEKDAY_SHORT[day.weekday()]} {day.strftime('%d.%m')} — {pair}")
    await query.message.edit_text(
        "\n".join(lines),
        reply_markup=_back_markup("offh_report_home"),
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

    if data.startswith("offh_day:"):
        _, venue, visit_date = data.split(":", 2)
        if venue not in VENUES:
            await query.answer("Неизвестное заведение.", show_alert=True)
            return OFFHOURS_VISITS_MENU
        await query.answer()
        await _render_day(query, venue, visit_date)
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
        elif result.code == "user_venue_month_full":
            venue_name = escape(str(result.details.get("venue_name", VENUES.get(venue, "заведение"))))
            month = escape(str(result.details.get("month", "текущем месяце")))
            await query.answer(
                f"Лимит достигнут: {venue_name} можно бронировать не более 2 раз за {month}.",
                show_alert=True,
            )
        else:
            await query.answer("Не удалось создать бронь. Проверьте дату и попробуйте снова.", show_alert=True)
        return OFFHOURS_VISITS_MENU

    if data == "offh_cancel_menu":
        await query.answer()
        bookings = await OffhoursVisitService.from_default_storage().user_bookings(user_id)
        buttons = [
            [
                InlineKeyboardButton(
                    f"❌ {VENUES.get(str(item.get('venue')), 'Заведение')} · {str(item.get('visit_date'))[5:]}",
                    callback_data=f"offh_cancel:{item['booking_id']}",
                )
            ]
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


async def coordinator_bookings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    group = await get_user_group(query.from_user.id)
    if group not in {"coor A", "coor R", "SPV", "MNG"}:
        await query.answer("Полный список доступен только руководителям.", show_alert=True)
        return ConversationHandler.END

    data = str(query.data or "")
    if data in {"offh_report_home", "offh_report_close"}:
        await query.answer()
        await query.message.edit_text(
            "📋 <b>Брони</b>\n\nВыберите заведение, чтобы открыть его расписание:",
            reply_markup=coordinator_venues_markup(),
            parse_mode="HTML",
        )
        return OFFHOURS_VISITS_MENU

    if data.startswith("offh_report_venue:"):
        venue = data.split(":", 1)[1]
        if venue not in VENUES:
            await query.answer("Неизвестное заведение.", show_alert=True)
            return OFFHOURS_VISITS_MENU
        await query.answer()
        await _render_coordinator_report(query, venue)
        return OFFHOURS_VISITS_MENU

    await query.answer()
    return OFFHOURS_VISITS_MENU


async def show_coordinator_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group = await get_user_group(update.effective_user.id)
    if group not in {"coor A", "coor R", "SPV", "MNG"}:
        await update.message.reply_text(
            "⛔️ Полный список броней доступен только координаторам, супервайзеру и менеджеру."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "📋 <b>Брони</b>\n\nВыберите заведение, чтобы открыть его расписание:",
        reply_markup=coordinator_venues_markup(),
        parse_mode="HTML",
    )
    return OFFHOURS_VISITS_MENU


__all__ = [
    "my_bookings_markup",
    "coordinator_bookings_callback",
    "coordinator_venues_markup",
    "offhours_home_markup",
    "offhours_visit_callback",
    "open_offhours_visits",
    "show_coordinator_bookings",
    "venue_dates_markup",
]
