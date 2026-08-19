"""Рассылка текста и фотографий администратором."""
from bot_context import *
from storage import load_json
from keyboards import cancel_keyboard, get_main_keyboard


async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ У вас нет доступа.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📢 Отправьте фото с подписью или обычный текст для рассылки:",
        reply_markup=cancel_keyboard,
    )
    return BROADCAST


async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    has_photo = bool(message.photo)
    text = (message.text or message.caption or "").strip()
    if not has_photo and not text:
        await message.reply_text("⚠️ Отправьте фото с подписью или текстовое сообщение.")
        return BROADCAST

    photo_id = message.photo[-1].file_id if has_photo else None
    users = await load_json(USERS_FILE)
    sent, failed = 0, 0
    status_msg = await message.reply_text("⏳ Идет рассылка...")

    for user_id in users.keys():
        if not str(user_id).isdigit():
            continue
        try:
            if has_photo:
                await context.bot.send_photo(chat_id=int(user_id), photo=photo_id, caption=text or None)
            else:
                await context.bot.send_message(chat_id=int(user_id), text=text)
            sent += 1
        except Exception as error:
            failed += 1
            logging.warning("Рассылка не доставлена пользователю %s: %s", user_id, error)

    await status_msg.edit_text(
        f"✅ Рассылка завершена!\nУспешно: `{sent}` | Ошибок: `{failed}`",
        parse_mode="Markdown",
    )
    await message.reply_text("Главное меню:", reply_markup=get_main_keyboard(update.effective_user.id))
    return ConversationHandler.END
