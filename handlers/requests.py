"""Единый inbox заявок пользователей для администратора."""
from telegram.error import TelegramError

from bot_context import (
    ContextTypes,
    ConversationHandler,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    logging,
)
from config import (
    ADMIN_ID,
    GROUPS_FILE,
    PENDING_FILE,
    USERS_FILE,
)
from data_models import (
    make_group_record,
    make_user_record,
    registration_request,
    user_name,
)
from keyboards import get_extra_keyboard, get_main_keyboard, get_registration_group_keyboard
from navigation import main_menu_markup
from permissions import Permission, has_permission
from states import (
    EXTRA_MENU_STATE,
    PENDING_REQUESTS_STATE,
)
from storage import load_pending, update_many_json


def _request_title(request: dict) -> str:
    kind = request.get("kind")
    if kind == "registration":
        return "Регистрация"
    if kind == "team":
        return f"Команда: {request.get('team', '—')}"
    return "Пользовательская заявка"


def _request_name(request: dict) -> str:
    return str(request.get("name") or request.get("user_id") or "Пользователь").strip()


def _short_text(value: str, limit: int = 70) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def process_registration_approval(user_id: str, accepted: bool) -> dict | None:
    """Единая согласованная операция для одобрения или отклонения регистрации."""
    user_id = str(user_id)

    def mutate(files: dict[str, dict]) -> dict | None:
        pending = files[PENDING_FILE]
        removed_request = pending.pop(user_id, None)
        if removed_request is None:
            return None

        request = registration_request(removed_request, user_id=user_id)
        name = user_name(request, "Пользователь")
        group = request.get("group")
        if accepted:
            files[USERS_FILE][user_id] = make_user_record(name)
            files[GROUPS_FILE][user_id] = make_group_record(name, group or "")
            user_text = f"🎉 Ваша заявка одобрена!\n\nДобро пожаловать, {name}!\nГруппа: {group}"
        else:
            files[GROUPS_FILE].pop(user_id, None)
            user_text = "❌ Заявка отклонена. Выберите группу заново, чтобы отправить новую заявку."
        return {"request": request, "name": name, "group": group, "user_text": user_text}

    return await update_many_json((PENDING_FILE, USERS_FILE, GROUPS_FILE), mutate)


async def load_request_inbox() -> list[dict]:
    """Возвращает все активные заявки в едином типизированном формате."""
    inbox: list[dict] = []

    pending = await load_pending()
    for user_id, raw_request in pending.items():
        request = registration_request(raw_request, user_id=user_id)
        group = request.get("group", "—")
        inbox.append(
            {
                "id": f"registration:{user_id}",
                "kind": "registration",
                "user_id": str(user_id),
                "name": str(request.get("name", user_id)),
                "group": group,
                "text": f"Выбранная группа: {group}.",
                "created_at": request.get("created_at", ""),
            }
        )

    inbox.sort(key=lambda item: item.get("created_at", ""))
    return inbox


def build_requests_markup(inbox: list[dict]) -> InlineKeyboardMarkup:
    keyboard = []
    for request in inbox:
        request_id = request["id"]
        title = _request_title(request)
        name = _request_name(request)
        preview = _short_text(request.get("text", ""))
        keyboard.append([InlineKeyboardButton(f"{title}: {name}", callback_data=f"req_view:{request_id}")])
        if preview:
            keyboard.append([InlineKeyboardButton(f"📝 {preview}", callback_data=f"req_view:{request_id}")])
        keyboard.append(
            [
                InlineKeyboardButton("✅ Принять", callback_data=f"req_accept:{request_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"req_reject:{request_id}"),
            ]
        )
    keyboard.append([InlineKeyboardButton("🔄 Обновить", callback_data="req_refresh")])
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="req_back")])
    return InlineKeyboardMarkup(keyboard)


async def show_requests_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, context, Permission.REGISTRATION_REQUESTS):
        await update.message.reply_text("⛔️ У вас нет доступа к этому разделу.")
        return ConversationHandler.END

    inbox = await load_request_inbox()
    if not inbox:
        await update.message.reply_text(
            "📂 Заявок нет. Все заявки обработаны.",
            reply_markup=get_extra_keyboard(),
            )
        return EXTRA_MENU_STATE

    lines = [f"📥 Заявки ({len(inbox)})\n"]
    for index, request in enumerate(inbox, start=1):
        lines.append(
            f"{index}. {_request_title(request)} — {_request_name(request)}\n"
            f"   {_short_text(request.get('text', ''))}"
        )

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=build_requests_markup(inbox),
    )
    return PENDING_REQUESTS_STATE


async def _show_admin_main_menu_after_callback(query, context: ContextTypes.DEFAULT_TYPE, status: str | None = None):
    await query.message.edit_text(status or "✅ Заявка обработана.")
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="🏠 Главное меню администратора:",
        reply_markup=main_menu_markup(ADMIN_ID, context),
    )
    return ConversationHandler.END


async def _show_requests_after_callback(query, context: ContextTypes.DEFAULT_TYPE, status: str | None = None):
    inbox = await load_request_inbox()
    if not inbox:
        await query.message.edit_text(status or "✅ Заявка обработана. Активных заявок больше нет.")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⚙️ Раздел «Дополнительно»:",
            reply_markup=get_extra_keyboard(),
        )
        return EXTRA_MENU_STATE

    lines = [status or f"📥 Заявки ({len(inbox)})\n"]
    for index, request in enumerate(inbox, start=1):
        lines.append(
            f"{index}. {_request_title(request)} — {_request_name(request)}\n"
            f"   {_short_text(request.get('text', ''))}"
        )
    await query.message.edit_text(
        "\n".join(lines),
        reply_markup=build_requests_markup(inbox),
    )
    return PENDING_REQUESTS_STATE


async def requests_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not has_permission(query.from_user.id, context, Permission.REGISTRATION_REQUESTS):
        await query.answer("⛔️ Нет доступа.", show_alert=True)
        return PENDING_REQUESTS_STATE
    await query.answer()

    action, raw_id = query.data.split(":", 1) if ":" in query.data else (query.data, "")
    if action == "req_back":
        await query.message.delete()
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⚙️ Раздел «Дополнительно»:",
            reply_markup=get_extra_keyboard(),
        )
        return EXTRA_MENU_STATE
    if action == "req_refresh":
        return await _show_requests_after_callback(query, context)
    if action == "req_view":
        inbox = await load_request_inbox()
        request = next((item for item in inbox if item["id"] == raw_id), None)
        if not request:
            return await _show_requests_after_callback(query, context)
        detail = (
            f"📥 {_request_title(request)}\n"
            f"👤 Пользователь: {_request_name(request)}\n"
            f"👥 Группа: {request.get('group', '—')}\n"
            f"🆔 Telegram ID: {request.get('user_id', '—')}\n\n"
            f"📝 {request.get('text', 'Без текста') or 'Без текста'}"
        )
        await query.message.edit_text(detail, reply_markup=build_requests_markup([request]))
        return PENDING_REQUESTS_STATE

    if action not in {"req_accept", "req_reject"}:
        return PENDING_REQUESTS_STATE

    inbox = await load_request_inbox()
    request = next((item for item in inbox if item["id"] == raw_id), None)
    if not request:
        await query.answer("Заявка уже обработана.", show_alert=True)
        return await _show_admin_main_menu_after_callback(query, context, "ℹ️ Заявка уже обработана.")

    accepted = action == "req_accept"
    kind = request["kind"]
    user_id = str(request.get("user_id", ""))
    if kind == "registration":
        result = await process_registration_approval(user_id, accepted)
        if result is None:
            return await _show_requests_after_callback(query, context)
        user_text = result["user_text"]

    else:
        return await _show_requests_after_callback(query, context, "⚠️ Этот тип заявки больше не поддерживается.")

    if user_id.isdigit():
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text=user_text,
                reply_markup=(
                    get_main_keyboard(int(user_id), request.get("group"))
                    if accepted
                    else get_registration_group_keyboard()
                ),
            )
        except TelegramError as error:
            logging.warning("Не удалось уведомить пользователя по заявке %s: %s", user_id, error)

    result = "✅ Заявка принята." if accepted else "❌ Заявка отклонена."
    return await _show_admin_main_menu_after_callback(query, context, result)
