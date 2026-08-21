"""Административные разделы: пользователи, заявки и удаление сотрудников."""
from telegram.error import TelegramError

from application.admin_service import EmployeeAdminService
from application.employee_service import EmployeeService
from bot_context import (
    ContextTypes,
    ConversationHandler,
    Update,
    logging,
)
from config import ADMIN_ID
from handlers.requests import (
    _show_requests_after_callback,
    process_registration_approval,
    requests_callback,
    show_requests_menu,
)
from keyboards import cancel_keyboard, get_extra_keyboard, get_main_keyboard
from navigation import main_menu_markup
from permissions import Permission, has_permission, set_admin_mode
from roles import get_user_group
from services import notify_user_bot_stopped
from states import (
    DELETE_BY_NUM_STATE,
    EXTRA_MENU_STATE,
    PENDING_REQUESTS_STATE,
)
from storage import load_pending


def _pending_request_name(raw_request) -> str:
    if isinstance(raw_request, dict):
        return str(raw_request.get("name") or "Пользователь")
    return str(raw_request)


async def enter_admin_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ Команда доступна только администратору.")
        return ConversationHandler.END
    set_admin_mode(context, True, user_id=update.effective_user.id)
    await update.message.reply_text(
        "🛡 **Режим администратора включён.**\nДля возврата в режим coor R используйте /coor.",
        reply_markup=main_menu_markup(ADMIN_ID, context),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def exit_admin_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ Команда доступна только администратору.")
        return ConversationHandler.END
    set_admin_mode(context, False, user_id=update.effective_user.id)
    group = await get_user_group(ADMIN_ID) or "coor R"
    await update.message.reply_text(
        "👥 **Режим coor R включён.**\nДля возврата к административным функциям используйте /admin.",
        reply_markup=main_menu_markup(ADMIN_ID, context, group=group),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def open_extra_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, context, Permission.ADMIN_PANEL):
        await update.message.reply_text("⛔️ У вас нет доступа к этому разделу.")
        return ConversationHandler.END

    await update.message.reply_text(
        "⚙️ **Раздел «Дополнительно»**\n\nВыберите необходимое действие:",
        reply_markup=get_extra_keyboard(),
        parse_mode="Markdown",
    )
    return EXTRA_MENU_STATE


async def show_registered_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, context, Permission.USER_MANAGEMENT):
        await update.message.reply_text("⛔️ У вас нет доступа к этой команде.")
        return ConversationHandler.END

    employee_service = EmployeeService.from_default_storage()
    users_data = await employee_service.users.load()
    registry = await employee_service.list_registry()
    registered_ids = {str(user_id) for user_id in users_data if str(user_id).isdigit()}
    response_parts = [f"👥 **Все пользователи ({len(registry)}):**\n"]
    user_index_map = {}

    if registry:
        for current_index, employee in enumerate(registry, start=1):
            aliases = {str(alias) for alias in employee.get("aliases", [])}
            registered_id = next((alias for alias in aliases if alias in registered_ids), None)
            is_registered = registered_id is not None
            marker = "✅" if is_registered else "❌"
            display_id = registered_id or employee.get("user_id") or "—"
            group = employee.get("group") or "—"
            user_index_map[current_index] = {
                "uid": registered_id or employee.get("user_id"),
                "name": employee["name"],
                "registered": is_registered,
            }
            response_parts.append(
                f"{current_index}. {marker} *{employee['name']}* — ID: `{display_id}` — Группа: **{group}**"
            )
    else:
        response_parts.append("_Список пользователей пуст._")

    context.user_data["user_index_map"] = user_index_map
    await update.message.reply_text(
        "\n".join(response_parts),
        reply_markup=get_extra_keyboard(),
        parse_mode="Markdown",
    )
    return EXTRA_MENU_STATE


async def show_pending_requests_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Legacy alias: экран заявок всегда строится единым inbox-обработчиком."""
    return await show_requests_menu(update, context)


async def pending_requests_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Совместимость со старыми кнопками через единый inbox-обработчик."""
    query = update.callback_query
    data = query.data
    if data == "pend_back":
        await query.answer()
        await query.message.delete()
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⚙️ Раздел «Дополнительно»:",
            reply_markup=get_extra_keyboard(),
        )
        return EXTRA_MENU_STATE

    await query.answer()
    pending = await load_pending()
    if data == "pend_accept_all":
        approved_count = 0
        for uid_str in list(pending):
            result = await process_registration_approval(uid_str, accepted=True)
            if result is None:
                continue
            approved_count += 1
            try:
                await context.bot.send_message(
                    chat_id=int(uid_str),
                    text=result["user_text"],
                    reply_markup=get_main_keyboard(int(uid_str), result["group"]),
                )
            except TelegramError as error:
                logging.warning("Не удалось уведомить пользователя %s: %s", uid_str, error)
        return await _show_requests_after_callback(
            query,
            context,
            f"✅ Одобрено заявок: {approved_count}.",
        )

    if data.startswith("pend_accept:"):
        _, uid_str = data.split(":", 1)
        result = await process_registration_approval(uid_str, accepted=True)
        if result is None:
            await query.answer("Эта заявка уже обработана или удалена.", show_alert=True)
            return await _show_requests_after_callback(query, context)
        try:
            await context.bot.send_message(
                chat_id=int(uid_str),
                text=result["user_text"],
                reply_markup=get_main_keyboard(int(uid_str), result["group"]),
            )
        except TelegramError as error:
            logging.warning("Не удалось уведомить пользователя %s: %s", uid_str, error)
        return await _show_requests_after_callback(
            query,
            context,
            f"✅ Заявка пользователя *{result['name']}* одобрена.",
        )

    return PENDING_REQUESTS_STATE


async def request_user_number_to_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, context, Permission.USER_MANAGEMENT):
        await update.message.reply_text("⛔️ У вас нет доступа к этой команде.")
        return ConversationHandler.END

    if "user_index_map" not in context.user_data or not context.user_data["user_index_map"]:
        await update.message.reply_text(
            "⚠️ Список пользователей пуст или устарел. Сначала нажмите **👥 Пользователи**.",
            reply_markup=get_extra_keyboard(),
            parse_mode="Markdown",
        )
        return EXTRA_MENU_STATE

    await update.message.reply_text(
        "🔢 **Удаление пользователя по номеру**\n\n"
        "Введите порядковый номер пользователя из списка для удаления:",
        reply_markup=cancel_keyboard,
        parse_mode="Markdown",
    )
    return DELETE_BY_NUM_STATE


async def process_delete_user_by_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, context, Permission.USER_MANAGEMENT):
        await update.message.reply_text("⛔️ У вас нет доступа к этой команде.")
        return ConversationHandler.END

    input_text = update.message.text.strip()

    if not input_text.isdigit():
        await update.message.reply_text(
            "❌ **Ошибка.** Пожалуйста, введите корректный порядковый номер (число):",
            parse_mode="Markdown",
        )
        return DELETE_BY_NUM_STATE

    num = int(input_text)
    user_map = context.user_data.get("user_index_map", {})

    if num not in user_map:
        await update.message.reply_text(
            f"❌ **Пользователь с номером `{num}` не найден.**\n\nПроверьте список и введите номер повторно:",
            parse_mode="Markdown",
        )
        return DELETE_BY_NUM_STATE

    target_user = user_map[num]
    target_uid = target_user.get("uid")
    target_name = target_user["name"]

    if not target_uid:
        await update.message.reply_text(
            "ℹ️ Эта запись есть в KPI/выдачах, но Telegram-пользователь ещё не зарегистрирован. "
            "Удаление по номеру доступно только для записей users.json.",
            reply_markup=get_extra_keyboard(),
        )
        return EXTRA_MENU_STATE

    operation = await EmployeeAdminService.from_default_storage().delete_registered(
        target_uid,
        update.effective_user.id,
    )
    if not operation.ok:
        await update.message.reply_text(
            "⚠️ Пользователь уже удалён или больше не зарегистрирован.",
            reply_markup=get_extra_keyboard(),
        )
        return EXTRA_MENU_STATE

    await notify_user_bot_stopped(context, target_uid)

    del user_map[num]
    context.user_data["user_index_map"] = user_map

    await update.message.reply_text(
        f"✅ **Пользователь под №{num} (*{target_name}*) успешно удалён!**",
        reply_markup=get_extra_keyboard(),
        parse_mode="Markdown",
    )
    return EXTRA_MENU_STATE


async def admin_moderation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает старые adm_* кнопки через тот же canonical req_* поток."""
    query = update.callback_query
    action, target_id_str = query.data.split(":", 1)
    if action not in {"adm_accept", "adm_reject"}:
        return
    original_data = query.data
    query.data = f"{'req_accept' if action == 'adm_accept' else 'req_reject'}:registration:{target_id_str}"
    try:
        return await requests_callback(update, context)
    finally:
        query.data = original_data
