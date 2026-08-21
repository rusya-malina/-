"""Coordinator delivery and employee retrieval flows for training files."""
from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram.error import TelegramError

from application.training_service import TRAINING_ONE, TRAINING_TWO, TrainingService
from bot_context import (
    ContextTypes,
    ConversationHandler,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    logging,
)
from config import (
    BOT_TIMEZONE,
    GROUPS_FILE,
    GROUPS_WITH_COACHING,
    GROUPS_WITH_MY_TRAINING,
    GROUPS_WITH_TRAINING,
    ISSUANCE_FILE,
    KPI_FILE,
    TRAINING_ONE_FILE,
    TRAINING_TWO_FILE,
    USERS_FILE,
)
from github_sync import sync_training_history
from keyboards import cancel_keyboard
from organization import ORG_STRUCTURE, get_visible_users
from roles import get_group_from_record, get_user_group
from states import MY_TRAINING_MENU, TRAINING_EMPLOYEE, TRAINING_TYPE, TRAINING_UPLOAD
from storage import load_json

TRAINING_LABELS = {TRAINING_ONE: "Обучение один", TRAINING_TWO: "Обучение два"}
TRAINING_FILE_PATHS = {TRAINING_ONE: TRAINING_ONE_FILE, TRAINING_TWO: TRAINING_TWO_FILE}
TRAINING_OTHER_TYPES = {TRAINING_ONE: TRAINING_TWO, TRAINING_TWO: TRAINING_ONE}


def is_training_group(group: str | None) -> bool:
    return group in GROUPS_WITH_TRAINING


def is_my_training_group(group: str | None) -> bool:
    return group in GROUPS_WITH_MY_TRAINING


def is_coaching_group(group: str | None) -> bool:
    return group in GROUPS_WITH_COACHING


def coaching_counts_from_data(history: dict, employee: dict) -> dict[str, int]:
    counts = {TRAINING_ONE: 0, TRAINING_TWO: 0}
    aliases = employee.get("aliases") or [employee.get("user_id")]
    for alias in aliases:
        record = history.get(str(alias), {})
        deliveries = record.get("deliveries", []) if isinstance(record, dict) else []
        if not isinstance(deliveries, list):
            continue
        for delivery in deliveries:
            if isinstance(delivery, dict) and delivery.get("type") in counts:
                counts[delivery["type"]] += 1
    return counts


def build_coaching_text(manager_group: str, employees: list[dict], history: dict) -> str:
    lines = [f"📚 **Коучинги команды — {manager_group}**", ""]
    if not employees:
        lines.append("_Нет зарегистрированных сотрудников в подчинённой команде._")
        return "\n".join(lines)
    for index, employee in enumerate(employees, start=1):
        counts = coaching_counts_from_data(history, employee)
        total = counts[TRAINING_ONE] + counts[TRAINING_TWO]
        lines.append(
            f"{index}. {employee['name']} — **{total}** коуч. "
            f"(обучение 1: {counts[TRAINING_ONE]}, обучение 2: {counts[TRAINING_TWO]})"
        )
    return "\n".join(lines)


def coaching_candidates(visible_users: list[dict], manager_group: str) -> list[dict]:
    child_groups = set(ORG_STRUCTURE.get(manager_group, {}).get("children", ()))
    return [employee for employee in visible_users if employee.get("group") in child_groups]


def training_candidates(visible_users: list[dict]) -> list[dict]:
    """Keep only employees with a numeric Telegram target for delivery."""
    candidates: list[dict] = []
    for employee in visible_users:
        telegram_id = next((str(alias) for alias in employee.get("aliases", []) if str(alias).isdigit()), None)
        if not telegram_id:
            continue
        candidates.append({"user_id": telegram_id, "name": employee["name"], "group": employee.get("group") or "—"})
    return sorted(candidates, key=lambda item: item["name"].casefold())


def training_markup(candidates: list[dict]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(item["name"], callback_data=f"training_user:{item['user_id']}")]
            for item in candidates
        ]
        or [[InlineKeyboardButton("Нет зарегистрированных сотрудников", callback_data="training_empty")]]
    )


def training_type_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Обучение один", callback_data="training_type:one")],
            [InlineKeyboardButton("Обучение два", callback_data="training_type:two")],
        ]
    )


def my_training_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Обучение 1", callback_data="my_training:one")],
            [InlineKeyboardButton("Обучение 2", callback_data="my_training:two")],
        ]
    )


def _training_month() -> str:
    return datetime.now(ZoneInfo(BOT_TIMEZONE)).strftime("%Y-%m")


def _clear_training_context(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in ("training_recipient_id", "training_recipient_name", "training_type"):
        context.user_data.pop(key, None)


async def _visible_training_candidates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[str | None, list[dict]]:
    user_id = update.effective_user.id
    group = await get_user_group(user_id)
    if not is_training_group(group):
        return group, []

    users = await load_json(USERS_FILE)
    groups = await load_json(GROUPS_FILE)
    kpi_data = await load_json(KPI_FILE)
    issuance_data = await load_json(ISSUANCE_FILE)
    visible = get_visible_users(
        user_id,
        users,
        groups,
        exclude_user_id=user_id,
        kpi_data=kpi_data,
        issuance_data=issuance_data,
    )
    return group, training_candidates(visible)


async def open_coaching_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group = await get_user_group(update.effective_user.id)
    if not is_coaching_group(group):
        await update.message.reply_text("⛔️ Раздел «Коучинги» доступен только coor A и coor R.")
        return ConversationHandler.END

    users = await load_json(USERS_FILE)
    groups = await load_json(GROUPS_FILE)
    kpi_data = await load_json(KPI_FILE)
    issuance_data = await load_json(ISSUANCE_FILE)
    history = await TrainingService.from_default_storage().history.load()
    visible = get_visible_users(
        update.effective_user.id,
        users,
        groups,
        exclude_user_id=update.effective_user.id,
        kpi_data=kpi_data,
        issuance_data=issuance_data,
    )
    employees = coaching_candidates(visible, group)
    await update.message.reply_text(build_coaching_text(group, employees, history), parse_mode="Markdown")
    return ConversationHandler.END


async def open_training_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group, candidates = await _visible_training_candidates(update, context)
    if not is_training_group(group):
        await update.message.reply_text("⛔️ Загрузка обучения доступна только Core/coor A и Core/coor R.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📚 **Загрузить обучение**\n\nВыберите сотрудника:",
        reply_markup=training_markup(candidates),
        parse_mode="Markdown",
    )
    return TRAINING_EMPLOYEE


async def training_employee_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "training_empty":
        await query.answer("В вашей команде нет зарегистрированных сотрудников.", show_alert=True)
        return TRAINING_EMPLOYEE
    await query.answer()
    if not query.data.startswith("training_user:"):
        return TRAINING_EMPLOYEE

    target_id = query.data.split(":", 1)[1]
    group, candidates = await _visible_training_candidates(update, context)
    allowed = next((item for item in candidates if item["user_id"] == target_id), None)
    if not is_training_group(group) or allowed is None:
        await query.answer("Сотрудник недоступен в вашей команде.", show_alert=True)
        return TRAINING_EMPLOYEE

    context.user_data["training_recipient_id"] = target_id
    context.user_data["training_recipient_name"] = allowed["name"]
    await query.message.edit_text(
        f"✅ Выбран сотрудник: **{allowed['name']}**\n\nВыберите тип обучения:",
        reply_markup=training_type_markup(),
        parse_mode="Markdown",
    )
    return TRAINING_TYPE


async def training_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query.data.startswith("training_type:"):
        await query.answer()
        return TRAINING_TYPE

    training_type = query.data.split(":", 1)[1]
    if training_type not in TRAINING_LABELS:
        await query.answer()
        return TRAINING_TYPE
    recipient_id = str(context.user_data.get("training_recipient_id", ""))
    recipient_name = str(context.user_data.get("training_recipient_name", "Сотрудник"))
    service = TrainingService.from_default_storage()
    if await service.has_sent_this_month(recipient_id, training_type):
        other_type = TRAINING_OTHER_TYPES[training_type]
        await query.answer(
            f"{TRAINING_LABELS[training_type]} уже отправлено в этом месяце. "
            f"Выберите {TRAINING_LABELS[other_type].lower()}",
            show_alert=True,
        )
        return TRAINING_TYPE
    await query.answer()

    context.user_data["training_type"] = training_type
    await query.message.edit_text(
        f"✅ Выбрано: **{TRAINING_LABELS[training_type]}** для **{recipient_name}**.",
        parse_mode="Markdown",
    )
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            f"📚 Отправьте Excel-файл для сотрудника **{recipient_name}**.\n"
            "Поддерживаются файлы `.xlsx` и `.xls`."
        ),
        reply_markup=cancel_keyboard,
        parse_mode="Markdown",
    )
    return TRAINING_UPLOAD


async def _save_latest_training_file(document, context: ContextTypes.DEFAULT_TYPE, training_type: str) -> None:
    destination = Path(TRAINING_FILE_PATHS[training_type])
    await asyncio.to_thread(destination.parent.mkdir, parents=True, exist_ok=True)
    suffix = ".xlsx" if str(document.file_name or "").lower().endswith(".xlsx") else ".xls"
    fd, temporary_path = tempfile.mkstemp(prefix=".training_", suffix=suffix, dir=str(destination.parent))
    os.close(fd)
    temporary = Path(temporary_path)
    try:
        telegram_file = await context.bot.get_file(document.file_id)
        await telegram_file.download_to_drive(temporary_path)
        await asyncio.to_thread(temporary.replace, destination)
    finally:
        if await asyncio.to_thread(temporary.exists):
            await asyncio.to_thread(temporary.unlink)


async def process_training_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    recipient_id = str(context.user_data.get("training_recipient_id", ""))
    recipient_name = str(context.user_data.get("training_recipient_name", "Сотрудник"))
    training_type = str(context.user_data.get("training_type", ""))
    training_label = TRAINING_LABELS.get(training_type, "Обучение")
    if not recipient_id.isdigit() or training_type not in TRAINING_LABELS:
        await update.message.reply_text("ℹ️ Выбор обучения устарел. Нажмите «Загрузить обучение» ещё раз.")
        return ConversationHandler.END

    group, candidates = await _visible_training_candidates(update, context)
    if not is_training_group(group) or not any(item["user_id"] == recipient_id for item in candidates):
        await update.message.reply_text("⛔️ Сотрудник больше не входит в вашу команду.")
        _clear_training_context(context)
        return ConversationHandler.END

    document = update.message.document
    file_name = str(document.file_name or "").lower()
    if not file_name.endswith((".xlsx", ".xls")):
        await update.message.reply_text("⚠️ Отправьте Excel-файл с расширением `.xlsx` или `.xls`.")
        return TRAINING_UPLOAD

    try:
        await _save_latest_training_file(document, context, training_type)
        await context.bot.copy_message(
            chat_id=int(recipient_id),
            from_chat_id=update.message.chat_id,
            message_id=update.message.message_id,
        )
        result = await TrainingService.from_default_storage().record_delivery(
            recipient_id,
            recipient_name,
            training_type,
            update.effective_user.id,
            file_id=document.file_id,
        )
        if not result.ok:
            other_type = TRAINING_OTHER_TYPES.get(training_type)
            if other_type:
                text = (
                    f"{TRAINING_LABELS[training_type]} уже отправлено в этом месяце. "
                    f"Выберите {TRAINING_LABELS[other_type].lower()}"
                )
            else:
                text = "Обучение уже отправлено в этом месяце. Выберите другой тип обучения"
            await update.message.reply_text(text, reply_markup=training_markup(candidates))
            return TRAINING_EMPLOYEE
        await sync_training_history()
        try:
            await context.bot.send_message(
                chat_id=int(recipient_id),
                text=f"📚 Вам отправлено: {training_label}.",
            )
        except TelegramError as error:
            logging.warning("Файл обучения отправлен, но уведомление не доставлено %s: %s", recipient_id, error)
        await update.message.reply_text(
            f"✅ {training_label} отправлено сотруднику **{recipient_name}**.",
            reply_markup=training_markup(candidates),
            parse_mode="Markdown",
        )
    except (OSError, TelegramError) as error:
        logging.warning("Не удалось отправить обучение пользователю %s: %s", recipient_id, error)
        await update.message.reply_text(
            f"❌ Не удалось отправить {training_label} сотруднику **{recipient_name}**. Попробуйте ещё раз.",
            reply_markup=training_markup(candidates),
            parse_mode="Markdown",
        )
        return TRAINING_EMPLOYEE
    finally:
        _clear_training_context(context)

    return TRAINING_EMPLOYEE


async def open_my_training_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    group = await get_user_group(update.effective_user.id)
    if not is_my_training_group(group):
        await update.message.reply_text("⛔️ Раздел «Мои обучения» доступен только сотрудникам A LAMP и R LAMP.")
        return ConversationHandler.END
    await update.message.reply_text(
        "📚 **Мои обучения**\n\nВыберите обучение:",
        reply_markup=my_training_markup(),
        parse_mode="Markdown",
    )
    return MY_TRAINING_MENU


async def my_training_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    training_type = query.data.split(":", 1)[1] if ":" in query.data else ""
    if training_type not in TRAINING_FILE_PATHS:
        await query.answer()
        return MY_TRAINING_MENU
    group = await get_user_group(query.from_user.id)
    if not is_my_training_group(group):
        await query.answer("Раздел недоступен для вашей группы.", show_alert=True)
        return ConversationHandler.END
    await query.answer()

    history = await TrainingService.from_default_storage().history.load()
    file_id = TrainingService.latest_file_id_from_data(history, query.from_user.id, training_type)
    if file_id:
        try:
            await context.bot.send_document(
                chat_id=query.from_user.id,
                document=file_id,
                caption=f"📚 {TRAINING_LABELS[training_type]}",
            )
            await query.message.reply_text("Выберите обучение ещё раз:", reply_markup=my_training_markup())
            return MY_TRAINING_MENU
        except TelegramError as error:
            logging.warning("Не удалось выдать Telegram file_id для %s пользователю %s: %s", training_type, query.from_user.id, error)

    path = Path(TRAINING_FILE_PATHS[training_type])
    if not await asyncio.to_thread(path.exists):
        await query.message.reply_text(f"{TRAINING_LABELS[training_type]} пока не загружено.")
        return MY_TRAINING_MENU
    try:
        content = await asyncio.to_thread(path.read_bytes)
        await context.bot.send_document(
            chat_id=query.from_user.id,
            document=BytesIO(content),
            caption=f"📚 {TRAINING_LABELS[training_type]}",
        )
        await query.message.reply_text("Выберите обучение ещё раз:", reply_markup=my_training_markup())
    except (OSError, TelegramError) as error:
        logging.warning("Не удалось выдать %s пользователю %s: %s", training_type, query.from_user.id, error)
        await query.message.reply_text("Не удалось отправить файл. Попробуйте ещё раз.")
    return MY_TRAINING_MENU


def build_training_compliance_text(
    manager_group: str,
    employees: list[dict],
    history: dict,
    month: str | None = None,
) -> str:
    selected_month = month or _training_month()
    lines = [f"📚 **Контроль обучений — {manager_group}**", f"📆 Месяц: {selected_month}", ""]
    missing_count = 0
    for employee in employees:
        missing_types = TrainingService.missing_types_from_data(history, employee["user_id"], selected_month)
        if not missing_types:
            continue
        missing_count += 1
        missing_labels = ", ".join("1" if item == TRAINING_ONE else "2" for item in missing_types)
        lines.append(f"{missing_count}. {employee['name']} — не проведено обучение: **{missing_labels}**")
    if not employees:
        lines.append("_Нет зарегистрированных сотрудников в подчинённой команде._")
    elif missing_count == 0:
        lines.append("✅ Все сотрудники прошли оба обучения в текущем месяце.")
    return "\n".join(lines)


async def send_training_compliance_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    users = await load_json(USERS_FILE)
    groups = await load_json(GROUPS_FILE)
    kpi_data = await load_json(KPI_FILE)
    issuance_data = await load_json(ISSUANCE_FILE)
    history = await TrainingService.from_default_storage().history.load()
    month = _training_month()

    for manager_id, group_record in groups.items():
        manager_group = get_group_from_record(group_record)
        if not str(manager_id).isdigit() or not is_training_group(manager_group):
            continue
        visible = get_visible_users(
            int(manager_id),
            users,
            groups,
            exclude_user_id=manager_id,
            kpi_data=kpi_data,
            issuance_data=issuance_data,
        )
        employees = training_candidates(visible)
        report_text = build_training_compliance_text(manager_group, employees, history, month)
        try:
            await context.bot.send_message(chat_id=int(manager_id), text=report_text, parse_mode="Markdown")
        except TelegramError as error:
            logging.warning("Не удалось отправить четверговой training report %s: %s", manager_id, error)


__all__ = [
    "build_coaching_text",
    "build_training_compliance_text",
    "coaching_candidates",
    "is_coaching_group",
    "is_my_training_group",
    "is_training_group",
    "my_training_callback",
    "my_training_markup",
    "open_coaching_report",
    "open_my_training_menu",
    "open_training_menu",
    "process_training_file",
    "send_training_compliance_job",
    "training_candidates",
    "training_employee_callback",
    "training_markup",
    "training_type_callback",
    "training_type_markup",
]
