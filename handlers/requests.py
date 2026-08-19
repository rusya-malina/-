"""Единый inbox заявок пользователей для администратора."""
from bot_context import *
from storage import load_json, save_json, load_pending, save_pending
from keyboards import cancel_keyboard, get_extra_keyboard, get_main_keyboard


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


async def load_request_inbox() -> list[dict]:
    """Возвращает все активные заявки в едином типизированном формате."""
    inbox: list[dict] = []

    pending = await load_pending()
    for user_id, full_name in pending.items():
        inbox.append(
            {
                "id": f"registration:{user_id}",
                "kind": "registration",
                "user_id": str(user_id),
                "name": str(full_name),
                "text": "Запрос на регистрацию в боте.",
                "created_at": "",
            }
        )

    team_requests = await load_json(TEAM_REQUESTS_FILE)
    for user_id, request in team_requests.items():
        request = dict(request or {})
        request.update(
            {
                "id": f"team:{user_id}",
                "kind": "team",
                "user_id": str(user_id),
                "name": request.get("name", user_id),
                "text": f"Выбранная команда: {request.get('team', '—')}.",
            }
        )
        inbox.append(request)

    user_requests = await load_json(USER_REQUESTS_FILE)
    for request_id, request in user_requests.items():
        request = dict(request or {})
        request.update(
            {
                "id": f"user:{request_id}",
                "kind": "user",
                "user_id": str(request.get("user_id", "")),
                "name": request.get("name", request.get("user_id", "Пользователь")),
                "text": request.get("text", ""),
            }
        )
        inbox.append(request)

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
    if update.effective_user.id != ADMIN_ID:
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
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔️ Нет доступа.", show_alert=True)
        return PENDING_REQUESTS_STATE

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
            await query.answer("Заявка уже обработана.", show_alert=True)
            return await _show_requests_after_callback(query, context)
        detail = (
            f"📥 {_request_title(request)}\n"
            f"👤 Пользователь: {_request_name(request)}\n"
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
        return await _show_requests_after_callback(query, context)

    accepted = action == "req_accept"
    kind = request["kind"]
    user_id = str(request.get("user_id", ""))
    name = _request_name(request)

    if kind == "registration":
        pending = await load_pending()
        pending.pop(user_id, None)
        await save_pending(pending)
        if accepted:
            users = await load_json(USERS_FILE)
            users[user_id] = name
            await save_json(users, USERS_FILE)
            user_text = f"🎉 Ваша заявка одобрена!\n\nДобро пожаловать, {name}!"
        else:
            user_text = "❌ Ваша заявка на регистрацию отклонена администратором."
    elif kind == "team":
        team_requests = await load_json(TEAM_REQUESTS_FILE)
        team_requests.pop(user_id, None)
        await save_json(team_requests, TEAM_REQUESTS_FILE)
        team = request.get("team", "—")
        if accepted:
            teams = await load_json(TEAMS_FILE)
            teams[user_id] = {
                "name": name,
                "team": team,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            await save_json(teams, TEAMS_FILE)
            user_text = f"✅ Администратор подтвердил вашу команду: {team}."
        else:
            user_text = f"❌ Запрос на команду {team} отклонён администратором."
    else:
        user_requests = await load_json(USER_REQUESTS_FILE)
        user_requests.pop(raw_id.removeprefix("user:"), None)
        await save_json(user_requests, USER_REQUESTS_FILE)
        user_text = "✅ Ваша заявка рассмотрена администратором." if accepted else "❌ Ваша заявка отклонена администратором."

    if user_id.isdigit():
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text=user_text,
                reply_markup=get_main_keyboard(int(user_id)),
                    )
        except Exception as error:
            logging.warning("Не удалось уведомить пользователя по заявке %s: %s", user_id, error)

    result = "✅ Заявка принята." if accepted else "❌ Заявка отклонена."
    return await _show_requests_after_callback(query, context, f"{result}\n\n📥 Активные заявки:")


async def start_user_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 Опишите вашу заявку одним сообщением.\n\n"
        "Её получит администратор и рассмотрит в разделе «📥 Заявки».",
        reply_markup=cancel_keyboard,
    )
    return USER_REQUEST


async def process_user_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if len(text) < 3:
        await update.message.reply_text("⚠️ Напишите заявку подробнее, минимум 3 символа.", reply_markup=cancel_keyboard)
        return USER_REQUEST

    user_id = str(update.effective_user.id)
    users = await load_json(USERS_FILE)
    name = users.get(user_id, update.effective_user.full_name or user_id)
    user_requests = await load_json(USER_REQUESTS_FILE)
    request_id = f"{user_id}_{int(datetime.now(timezone.utc).timestamp())}"
    user_requests[request_id] = {
        "user_id": user_id,
        "name": name,
        "text": text,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await save_json(user_requests, USER_REQUESTS_FILE)

    await update.message.reply_text(
        "✅ Ваша заявка отправлена администратору.",
        reply_markup=get_main_keyboard(update.effective_user.id),
    )
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "🔔 Новая пользовательская заявка\n\n"
                f"👤 Пользователь: {name}\n"
                f"🆔 Telegram ID: {user_id}\n\n"
                f"📝 {text}"
            ),
                reply_markup=InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton("✅ Принять", callback_data=f"req_accept:user:{request_id}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"req_reject:user:{request_id}"),
                ]]
            ),
        )
    except Exception as error:
        logging.error("Не удалось отправить пользовательскую заявку админу: %s", error)
    return ConversationHandler.END
