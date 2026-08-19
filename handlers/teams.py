"""Выбор команды сотрудником и административное подтверждение."""
from bot_context import *
from storage import load_json, save_json
from keyboards import cancel_keyboard, get_main_keyboard, get_team_keyboard


async def start_team_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users = await load_json(USERS_FILE)
    if user_id not in users and update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "⚠️ Сначала завершите регистрацию через /start.",
            reply_markup=get_main_keyboard(update.effective_user.id),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "👥 **Выберите команду**\n\nПосле выбора заявка будет отправлена администратору на подтверждение.",
        reply_markup=get_team_keyboard(),
        parse_mode="Markdown",
    )
    return TEAM_SELECTION


async def process_team_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    selected_team = update.message.text.strip()
    if selected_team not in TEAM_OPTIONS:
        await update.message.reply_text("⚠️ Выберите команду кнопкой из списка.", reply_markup=get_team_keyboard())
        return TEAM_SELECTION

    users = await load_json(USERS_FILE)
    user_name = users.get(user_id, "Руслан Малинин" if update.effective_user.id == ADMIN_ID else "")
    if not user_name:
        await update.message.reply_text("⚠️ Пользователь ещё не зарегистрирован.", reply_markup=get_main_keyboard(update.effective_user.id))
        return ConversationHandler.END

    team_requests = await load_json(TEAM_REQUESTS_FILE)
    team_requests[user_id] = {
        "user_id": user_id,
        "name": user_name,
        "team": selected_team,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await save_json(team_requests, TEAM_REQUESTS_FILE)

    await update.message.reply_text(
        f"⏳ Заявка на команду **{selected_team}** отправлена администратору.\n"
        "После подтверждения команда будет назначена.",
        reply_markup=get_main_keyboard(update.effective_user.id),
        parse_mode="Markdown",
    )

    inline_keyboard = [[
        InlineKeyboardButton("✅ Подтвердить", callback_data=f"team_accept:{user_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"team_reject:{user_id}"),
    ]]
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                "🔔 **Запрос на определение команды**\n\n"
                f"👤 Сотрудник: *{user_name}*\n"
                f"🆔 Telegram ID: `{user_id}`\n"
                f"👥 Команда: **{selected_team}**"
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard),
            parse_mode="Markdown",
        )
    except Exception as error:
        logging.error("Не удалось отправить запрос команды администратору: %s", error)

    return ConversationHandler.END


async def team_moderation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        await query.message.edit_text("⛔️ У вас нет доступа к этому запросу.")
        return

    action, user_id = query.data.split(":", 1)
    team_requests = await load_json(TEAM_REQUESTS_FILE)
    request = team_requests.get(user_id)
    if not request:
        await query.answer("Запрос уже обработан или устарел.", show_alert=True)
        return

    selected_team = request["team"]
    user_name = request["name"]
    if action == "team_accept":
        teams = await load_json(TEAMS_FILE)
        teams[user_id] = {
            "name": user_name,
            "team": selected_team,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await save_json(teams, TEAMS_FILE)
        del team_requests[user_id]
        await save_json(team_requests, TEAM_REQUESTS_FILE)
        await query.message.edit_text(
            f"✅ **Команда подтверждена**\n\n{user_name} → **{selected_team}**",
            parse_mode="Markdown",
        )
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text=f"✅ Администратор подтвердил вашу команду: **{selected_team}**.",
                reply_markup=get_main_keyboard(int(user_id), selected_team),
                parse_mode="Markdown",
            )
        except Exception as error:
            logging.error("Не удалось уведомить пользователя о команде: %s", error)
    elif action == "team_reject":
        del team_requests[user_id]
        await save_json(team_requests, TEAM_REQUESTS_FILE)
        await query.message.edit_text(
            f"❌ **Запрос на команду отклонён**\n\n{user_name} → **{selected_team}**",
            parse_mode="Markdown",
        )
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text="❌ Запрос на выбранную команду отклонён администратором. Выберите новую группу через /start.",
                reply_markup=get_main_keyboard(int(user_id)),
            )
        except Exception as error:
            logging.error("Не удалось уведомить пользователя об отказе команды: %s", error)
