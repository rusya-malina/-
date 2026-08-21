"""Coordinator training Excel delivery flow."""
from __future__ import annotations

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
from config import GROUPS_FILE, GROUPS_WITH_TRAINING, ISSUANCE_FILE, KPI_FILE, USERS_FILE
from github_sync import sync_training_history
from keyboards import cancel_keyboard, get_main_keyboard
from navigation import main_menu_markup
from organization import get_visible_users
from roles import get_user_group
from states import TRAINING_EMPLOYEE, TRAINING_TYPE, TRAINING_UPLOAD
from storage import load_json

TRAINING_LABELS = {TRAINING_ONE: "Обучение один", TRAINING_TWO: "Обучение два"}


def is_training_group(group: str | None) -> bool:
    return group in GROUPS_WITH_TRAINING


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
    await query.answer()
    if query.data == "training_empty":
        await query.answer("В вашей команде нет зарегистрированных сотрудников.", show_alert=True)
        return TRAINING_EMPLOYEE
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
    await query.answer()
    if not query.data.startswith("training_type:"):
        return TRAINING_TYPE

    training_type = query.data.split(":", 1)[1]
    if training_type not in TRAINING_LABELS:
        return TRAINING_TYPE
    recipient_id = str(context.user_data.get("training_recipient_id", ""))
    recipient_name = str(context.user_data.get("training_recipient_name", "Сотрудник"))
    service = TrainingService.from_default_storage()
    if await service.has_sent_this_month(recipient_id, training_type):
        if training_type == TRAINING_ONE:
            await query.answer(
                "Обучение один уже было отправлено ранее. Выберите обучение два",
                show_alert=True,
            )
        else:
            await query.answer("Это обучение уже было отправлено в текущем месяце.", show_alert=True)
        return TRAINING_TYPE

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
        )
        if not result.ok:
            await update.message.reply_text(
                "Обучение один уже было отправлено ранее. Выберите обучение два",
                reply_markup=main_menu_markup(update.effective_user.id, context, group=group),
            )
            return ConversationHandler.END
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
            reply_markup=main_menu_markup(update.effective_user.id, context, group=group),
            parse_mode="Markdown",
        )
    except TelegramError as error:
        logging.warning("Не удалось отправить обучение пользователю %s: %s", recipient_id, error)
        await update.message.reply_text(
            f"❌ Не удалось отправить {training_label} сотруднику **{recipient_name}**. Попробуйте ещё раз.",
            reply_markup=get_main_keyboard(update.effective_user.id, group),
            parse_mode="Markdown",
        )
        return TRAINING_UPLOAD
    finally:
        _clear_training_context(context)

    return ConversationHandler.END


def _clear_training_context(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in ("training_recipient_id", "training_recipient_name", "training_type"):
        context.user_data.pop(key, None)


__all__ = [
    "is_training_group",
    "open_training_menu",
    "process_training_file",
    "training_candidates",
    "training_employee_callback",
    "training_markup",
    "training_type_callback",
    "training_type_markup",
]
