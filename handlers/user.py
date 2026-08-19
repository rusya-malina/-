"""Пользовательские сценарии: регистрация, расчёты и возврат в меню."""
from bot_context import *
from storage import load_json, save_json, load_pending, update_pending
from keyboards import cancel_keyboard, get_main_keyboard, get_registration_group_keyboard
from services import notify_user_bot_stopped
from roles import get_user_group
from organization import is_admin_mode


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = await load_json(USERS_FILE)
    user_id_num = update.effective_user.id
    user_id = str(user_id_num)

    if user_id_num == ADMIN_ID:
        context.user_data["name"] = users.get(user_id, "Руслан Малинин")
        admin_mode = bool(context.user_data.get("admin_mode"))
        group = await get_user_group(user_id_num) or "coor R"
        await update.message.reply_text(
            "👋 Вы вошли в режиме администратора." if admin_mode else "👋 Вы вошли в режиме coor R.",
            reply_markup=get_main_keyboard(ADMIN_ID, group=group, admin_mode=admin_mode),
        )
        return ConversationHandler.END

    if user_id in users:
        context.user_data["name"] = users[user_id]
        group = await get_user_group(user_id_num)
        await update.message.reply_text(
            f"👋 С возвращением, {users[user_id]}!",
            reply_markup=get_main_keyboard(user_id_num, group),
        )
        return ConversationHandler.END

    pending = await load_pending()
    if user_id in pending:
        request = pending[user_id] if isinstance(pending[user_id], dict) else {"group": "—"}
        await update.message.reply_text(
            f"⏳ Ваша заявка уже ожидает решения администратора.\nГруппа: {request.get('group', '—')}",
            reply_markup=ReplyKeyboardRemove(),
        )
        return ConversationHandler.END

    context.user_data.pop("reg_group", None)
    context.user_data.pop("reg_first_name", None)
    await update.message.reply_text(
        "👋 Здравствуйте!\n\nВыберите вашу группу для регистрации:",
        reply_markup=get_registration_group_keyboard(),
    )
    return REG_GROUP


async def reg_get_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(
            "👋 Вы вошли как администратор.",
            reply_markup=get_main_keyboard(
                ADMIN_ID,
                group=await get_user_group(ADMIN_ID) or "coor R",
                admin_mode=bool(context.user_data.get("admin_mode")),
            ),
        )
        return ConversationHandler.END

    selected_group = update.message.text.strip()
    if selected_group not in TEAM_OPTIONS:
        await update.message.reply_text(
            "⚠️ Выберите группу кнопкой из списка.",
            reply_markup=get_registration_group_keyboard(),
        )
        return REG_GROUP

    context.user_data["reg_group"] = selected_group
    await update.message.reply_text(
        f"✅ Группа выбрана: {selected_group}\n\nТеперь введите ваше **Имя**:",
        reply_markup=cancel_keyboard,
        parse_mode="Markdown",
    )
    return REG_FIRST_NAME


async def reg_get_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(
            "👋 Вы вошли как администратор.",
            reply_markup=get_main_keyboard(
                ADMIN_ID,
                group=await get_user_group(ADMIN_ID) or "coor R",
                admin_mode=bool(context.user_data.get("admin_mode")),
            ),
        )
        return ConversationHandler.END

    first_name = update.message.text.strip()
    if len(first_name) < 2:
        await update.message.reply_text("⚠️ Введите корректное имя:")
        return REG_FIRST_NAME

    context.user_data["reg_first_name"] = first_name
    await update.message.reply_text(
        "Отлично! Теперь введите вашу **Фамилию**:",
        reply_markup=cancel_keyboard,
        parse_mode="Markdown",
    )
    return REG_LAST_NAME


async def reg_get_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(
            "👋 Вы вошли как администратор.",
            reply_markup=get_main_keyboard(
                ADMIN_ID,
                group=await get_user_group(ADMIN_ID) or "coor R",
                admin_mode=bool(context.user_data.get("admin_mode")),
            ),
        )
        return ConversationHandler.END

    last_name = update.message.text.strip()
    if len(last_name) < 2:
        await update.message.reply_text("⚠️ Введите корректную фамилию:")
        return REG_LAST_NAME

    first_name = context.user_data.get("reg_first_name")
    full_name = f"{first_name} {last_name}"
    user_id_num = update.effective_user.id

    selected_group = context.user_data.get("reg_group")
    if selected_group not in TEAM_OPTIONS:
        await update.message.reply_text(
            "⚠️ Сначала выберите группу для регистрации.",
            reply_markup=get_registration_group_keyboard(),
        )
        return REG_GROUP

    context.user_data["pending_full_name"] = full_name
    context.user_data["pending_group"] = selected_group

    request_record = {
        "name": full_name,
        "group": selected_group,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    def add_pending(data):
        data[str(user_id_num)] = request_record
        return request_record

    await update_pending(add_pending)

    await update.message.reply_text(
        "⏳ **Заявка отправлена администратору.**\n\n"
        f"Группа: **{selected_group}**\n"
        "Пожалуйста, дождитесь подтверждения регистрации.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown",
    )

    inline_keyboard = [
        [
            InlineKeyboardButton("✅ Принять", callback_data=f"req_accept:registration:{user_id_num}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"req_reject:registration:{user_id_num}"),
        ]
    ]
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"🔔 **Новая заявка на регистрацию!**\n\n"
                f"👤 ФИО: *{full_name}*\n"
                f"👥 Группа: **{selected_group}**\n"
                f"🆔 Telegram ID: `{user_id_num}`"
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard),
            parse_mode="Markdown",
        )
    except Exception as e:
        logging.error(f"Не удалось отправить уведомление админу: {e}")

    return ConversationHandler.END


async def change_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = await load_json(USERS_FILE)
    user_id = str(update.effective_user.id)

    if user_id not in users:
        await update.message.reply_text(
            "⚠️ Вы еще не зарегистрированы. Сначала выберите группу:",
            reply_markup=get_registration_group_keyboard(),
        )
        return REG_GROUP

    await update.message.reply_text(
        "✏️ Введите ваше новое **Имя**:",
        reply_markup=cancel_keyboard,
        parse_mode="Markdown",
    )
    return CHANGE_NAME


async def save_new_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    first_name = update.message.text.strip()
    if len(first_name) < 2:
        await update.message.reply_text("⚠️ Введите корректное имя:")
        return CHANGE_NAME

    context.user_data["new_first_name"] = first_name
    await update.message.reply_text(
        "Отлично! Теперь введите вашу новую **Фамилию**:",
        reply_markup=cancel_keyboard,
        parse_mode="Markdown",
    )
    return CHANGE_LAST_NAME


async def save_new_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    last_name = update.message.text.strip()
    if len(last_name) < 2:
        await update.message.reply_text("⚠️ Введите корректную фамилию:")
        return CHANGE_LAST_NAME

    first_name = context.user_data.get("new_first_name")
    new_full_name = f"{first_name} {last_name}"
    user_id_num = update.effective_user.id

    users = await load_json(USERS_FILE)
    users[str(user_id_num)] = new_full_name
    await save_json(users, USERS_FILE)

    context.user_data["name"] = new_full_name

    await update.message.reply_text(
        f"✅ Имя и фамилия успешно изменены:\n👤 *{new_full_name}*",
        reply_markup=get_main_keyboard(
            user_id_num,
            group=await get_user_group(user_id_num),
            admin_mode=is_admin_mode(user_id_num, context),
        ),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def new_calculation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = await load_json(USERS_FILE)
    user_id = str(update.effective_user.id)

    group = await get_user_group(user_id)
    if user_id not in users or group not in TEAM_OPTIONS:
        await update.message.reply_text(
            "⚠️ Сначала завершите регистрацию: выберите группу.",
            reply_markup=get_registration_group_keyboard(),
        )
        return REG_GROUP

    context.user_data["name"] = users[user_id]
    await update.message.reply_text("📊 **Новый расчет**\n\nВведите количество **LAS**:", reply_markup=cancel_keyboard, parse_mode="Markdown")
    return LAS


async def get_las(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace(",", "."))
        if val < 0: raise ValueError
        context.user_data["las"] = val
        await update.message.reply_text("Введите количество **LAU**:", reply_markup=cancel_keyboard, parse_mode="Markdown")
        return LAU
    except ValueError:
        await update.message.reply_text("❌ Ошибка. Введите положительное число для LAS:")
        return LAS


async def get_lau(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace(",", "."))
        if val < 0: raise ValueError
        context.user_data["lau"] = val

        name = context.user_data["name"]
        las = context.user_data["las"]
        lau = context.user_data["lau"]
        total = las + lau
        las_percent = (las / total) * 100 if total > 0 else 0

        need_las = 0 if las_percent >= 40 else max(0, int(((0.4 * total) - las) / 0.6) + 1)

        result = (
            f"📊 **Результат расчета**\n👤 *{name}*\n"
            f"• LAS: `{las}` | LAU: `{lau}` | Сумма: `{total}`\n"
            f"• Итоговый LAS %: `{las_percent:.2f}%`\n"
        )
        if need_las > 0:
            result += f"⚠️ **Рекомендация:** Добавить LAS: `{need_las}`"
        else:
            result += "✅ **Показатель в норме!**"

        group = await get_user_group(update.effective_user.id)
        await update.message.reply_text(result, reply_markup=get_main_keyboard(update.effective_user.id, group), parse_mode="Markdown")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Ошибка. Введите положительное число для LAU:")
        return LAU


async def cancel_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for key in ("issuance_type", "issuance_user_id", "issuance_amount"):
        context.user_data.pop(key, None)
    group = await get_user_group(update.effective_user.id)
    await update.message.reply_text("❌ Действие отменено.", reply_markup=get_main_keyboard(update.effective_user.id, group))
    return ConversationHandler.END
