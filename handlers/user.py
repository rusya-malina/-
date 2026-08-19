"""Пользовательские сценарии: регистрация, расчёты и возврат в меню."""
from bot_context import *
from storage import load_json, save_json, load_pending, save_pending
from keyboards import cancel_keyboard, get_main_keyboard
from services import notify_user_bot_stopped


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = await load_json(USERS_FILE)
    user_id_num = update.effective_user.id
    user_id = str(user_id_num)

    if user_id in users:
        context.user_data["name"] = users[user_id]
        await update.message.reply_text(
            f"👋 С возвращением, {users[user_id]}!",
            reply_markup=get_main_keyboard(user_id_num),
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "👋 Здравствуйте!\n\n"
        "Для начала регистрации введите ваше **Имя**:",
        reply_markup=cancel_keyboard,
        parse_mode="Markdown",
    )
    return REG_FIRST_NAME


async def reg_get_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    last_name = update.message.text.strip()
    if len(last_name) < 2:
        await update.message.reply_text("⚠️ Введите корректную фамилию:")
        return REG_LAST_NAME

    first_name = context.user_data.get("reg_first_name")
    full_name = f"{first_name} {last_name}"
    user_id_num = update.effective_user.id

    context.user_data["pending_full_name"] = full_name

    pending = await load_pending()
    pending[str(user_id_num)] = full_name
    await save_pending(pending)

    await update.message.reply_text(
        "⏳ **Заявка отправлена администратору.**\n\n"
        "Пожалуйста, дождитесь подтверждения регистрации.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown",
    )

    inline_keyboard = [
        [
            InlineKeyboardButton("✅ Принять", callback_data=f"adm_accept:{user_id_num}:{full_name}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"adm_reject:{user_id_num}"),
        ]
    ]
    
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"🔔 **Новая заявка на регистрацию!**\n\n"
                f"👤 ФИО: *{full_name}*\n"
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
            "⚠️ Вы еще не зарегистрированы. Введите ваше **Имя**:",
            reply_markup=cancel_keyboard,
            parse_mode="Markdown",
        )
        return REG_FIRST_NAME

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
        reply_markup=get_main_keyboard(user_id_num),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def new_calculation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = await load_json(USERS_FILE)
    user_id = str(update.effective_user.id)

    if user_id not in users:
        await update.message.reply_text("⚠️ Сначала зарегистрируйтесь:", reply_markup=cancel_keyboard)
        return REG_FIRST_NAME

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

        await update.message.reply_text(result, reply_markup=get_main_keyboard(update.effective_user.id), parse_mode="Markdown")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Ошибка. Введите положительное число для LAU:")
        return LAU


async def cancel_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for key in ("issuance_type", "issuance_user_id", "issuance_amount"):
        context.user_data.pop(key, None)
    await update.message.reply_text("❌ Действие отменено.", reply_markup=get_main_keyboard(update.effective_user.id))
    return ConversationHandler.END
