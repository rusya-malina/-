"""Admin flow for uploading and activating the monthly KPI directory."""
from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from telegram.error import TelegramError

from application.monthly_kpi_service import MonthlyKpiService, MonthlyKpiValidationError
from bot_context import ContextTypes, ConversationHandler, InlineKeyboardButton, InlineKeyboardMarkup, Update, logging
from config import BOT_TIMEZONE, UPLOADED_DATA_DIR
from errors import StorageError
from keyboards import get_data_keyboard
from permissions import Permission, has_permission
from states import KPI_MENU_STATE, MONTHLY_KPI_UPLOAD


def _monthly_kpi_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Загрузить сейчас", callback_data="monthly_kpi_now")],
            [InlineKeyboardButton("📅 Загрузить в начале следующего месяца", callback_data="monthly_kpi_next")],
            [InlineKeyboardButton("❌ Отмена", callback_data="monthly_kpi_cancel")],
        ]
    )


def _remove_temp(path: str | None) -> None:
    if path and os.path.exists(path):
        os.remove(path)


def _is_header(row: list[object]) -> bool:
    values = [str(value or "").strip().casefold() for value in row]
    return bool(values) and any(value in {"kpi", "название kpi", "план", "вес", "weight"} for value in values)


def _read_monthly_kpi_excel(path: str) -> list[dict[str, object]]:
    frame = pd.read_excel(path, header=None, dtype=object)
    rows: list[dict[str, object]] = []
    for row in frame.iloc[:, :3].itertuples(index=False, name=None):
        values = list(row) + [None, None, None]
        if _is_header(values[:3]):
            continue
        if not str(values[0] or "").strip():
            continue
        rows.append({"name": values[0], "plan": values[1], "weight": values[2]})
    return rows


def _current_period() -> str:
    return datetime.now(ZoneInfo(BOT_TIMEZONE)).strftime("%Y-%m")


def _next_period(period: str) -> str:
    year, month = (int(part) for part in period.split("-"))
    return f"{year + 1:04d}-01" if month == 12 else f"{year:04d}-{month + 1:02d}"


async def start_monthly_kpi_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, context, Permission.KPI_MANAGEMENT):
        await update.message.reply_text("⛔️ У вас нет доступа к этому разделу.")
        return ConversationHandler.END
    await update.message.reply_text(
        "📅 **Загрузка месячного KPI**\n\n"
        "Отправьте Excel-файл из трёх колонок без обязательной строки заголовков:\n"
        "1. Название KPI\n2. План\n3. Вес\n\n"
        "Если сумма весов отличается от 100%, бот автоматически нормализует её. "
        "Нулевые и отрицательные веса будут отклонены.",

        parse_mode="Markdown",
    )
    return MONTHLY_KPI_UPLOAD


async def process_monthly_kpi_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if not document or not document.file_name.lower().endswith(".xlsx"):
        await update.message.reply_text("⚠️ Отправьте файл в формате `.xlsx`.", parse_mode="Markdown")
        return MONTHLY_KPI_UPLOAD

    file_path: str | None = None
    try:
        os.makedirs(UPLOADED_DATA_DIR, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=".monthly_kpi_", suffix=".xlsx", dir=UPLOADED_DATA_DIR, delete=False
        ) as temp_file:
            file_path = temp_file.name
        remote_file = await context.bot.get_file(document.file_id)
        await remote_file.download_to_drive(file_path)
        rows = await asyncio.to_thread(_read_monthly_kpi_excel, file_path)
        prepared = MonthlyKpiService.prepare(rows)
        period = _current_period()
        context.user_data["pending_monthly_kpi"] = {
            "prepared": prepared,
            "temp_path": file_path,
            "next_period": _next_period(period),
        }
        lines = [
            "🔎 **Проверка месячного KPI**",
            f"Текущий период: `{period}`",
            f"KPI в файле: **{prepared['row_count']}**",
            f"Сумма весов после проверки: **{prepared['total_weight']:.2f}%**",
        ]
        if prepared.get("weights_adjusted"):
            lines.append(
                f"⚠️ Веса нормализованы автоматически: "
                f"{prepared['original_total_weight']:.2f}% → {prepared['total_weight']:.2f}%"
            )
        lines.append("")
        for index, metric in enumerate(prepared["metrics"], start=1):
            lines.append(f"{index}. **{metric['name']}** — план: `{metric['plan']:g}`, вес: `{metric['weight']:g}%`")
        lines.extend(["", "Данные ещё не применены. Выберите срок загрузки:"])
        await update.message.reply_text("\n".join(lines), reply_markup=_monthly_kpi_markup(), parse_mode="Markdown")
        return MONTHLY_KPI_UPLOAD
    except MonthlyKpiValidationError as error:
        _remove_temp(file_path)
        await update.message.reply_text(f"⛔ **Ошибка проверки месячного KPI:** {error}", parse_mode="Markdown")
        return MONTHLY_KPI_UPLOAD
    except (OSError, StorageError, TelegramError, ValueError) as error:
        logging.exception("Ошибка загрузки месячного KPI Excel: %s", error)
        _remove_temp(file_path)
        await update.message.reply_text("❌ Не удалось прочитать месячный KPI Excel-файл. Проверьте формат и повторите загрузку.")
        return MONTHLY_KPI_UPLOAD


async def monthly_kpi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not has_permission(query.from_user.id, context, Permission.KPI_MANAGEMENT):
        await query.message.edit_text("⛔️ У вас нет доступа к загрузке месячного KPI.")
        return ConversationHandler.END

    staged = context.user_data.get("pending_monthly_kpi")
    if not isinstance(staged, dict):
        await query.message.edit_text("ℹ️ Предпросмотр устарел. Загрузите месячный KPI-файл заново.")
        return KPI_MENU_STATE

    temp_path = staged.get("temp_path")
    prepared = staged.get("prepared")
    context.user_data.pop("pending_monthly_kpi", None)
    if query.data == "monthly_kpi_cancel":
        _remove_temp(temp_path)
        await query.message.edit_text("❌ Загрузка месячного KPI отменена. Данные не изменены.")
        await context.bot.send_message(query.message.chat_id, "📥 Раздел загрузки данных:", reply_markup=get_data_keyboard())
        return KPI_MENU_STATE

    if not isinstance(prepared, dict) or query.data not in {"monthly_kpi_now", "monthly_kpi_next"}:
        _remove_temp(temp_path)
        await query.message.edit_text("ℹ️ Действие загрузки устарело. Загрузите файл заново.")
        return KPI_MENU_STATE

    try:
        service = MonthlyKpiService.from_default_storage()
        if query.data == "monthly_kpi_now":
            active = await service.activate_now(prepared)
            result_text = f"✅ Месячный KPI загружен сейчас и активирован для периода `{active['period']}`."
        else:
            pending = await service.schedule_next(prepared, staged.get("next_period"))
            result_text = f"✅ Месячный KPI сохранён и будет активирован в начале периода `{pending['period']}`."
        _remove_temp(temp_path)
        await query.message.edit_text(result_text)
        await context.bot.send_message(query.message.chat_id, "📥 Раздел загрузки данных:", reply_markup=get_data_keyboard())
        return KPI_MENU_STATE
    except (OSError, StorageError, TypeError, ValueError) as error:
        logging.exception("Ошибка применения месячного KPI: %s", error)
        _remove_temp(temp_path)
        await query.message.edit_text("❌ Не удалось сохранить месячный KPI. Рабочий справочник не изменён.")
        return KPI_MENU_STATE


__all__ = ["monthly_kpi_callback", "process_monthly_kpi_file", "start_monthly_kpi_upload"]
