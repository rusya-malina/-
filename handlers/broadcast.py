"""Рассылка текста, фотографий и документов администратором."""
from telegram.error import TelegramError

from bot_context import (
    ContextTypes,
    ConversationHandler,
    Update,
    logging,
)
from config import (
    USERS_FILE,
)
from keyboards import cancel_keyboard
from navigation import main_menu_markup
from permissions import Permission, has_permission
from states import (
    BROADCAST,
)
from storage import load_json


async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, context, Permission.BROADCAST):
        await update.message.reply_text("⛔️ У вас нет доступа.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📢 Отправьте обычный текст, фотографию с подписью или файл/Excel-документ "
        "(включая PPT/PPTX-презентации) с необязательной подписью для рассылки:",
        reply_markup=cancel_keyboard,
    )
    return BROADCAST


async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    has_photo = bool(message.photo)
    has_document = bool(message.document)
    has_text = bool(message.text)
    if not has_photo and not has_document and not has_text:
        await message.reply_text(
            "⚠️ Отправьте текст, фотографию или файл/документ."
        )
        return BROADCAST

    users = await load_json(USERS_FILE)
    sent, failed = 0, 0
    status_msg = await message.reply_text("⏳ Идет рассылка...")

    for user_id in users:
        if not str(user_id).isdigit():
            continue
        try:
            # Копирование исходного сообщения сохраняет файл, имя, фото,
            # подпись и текст без повторной загрузки через Bot API.
            await context.bot.copy_message(
                chat_id=int(user_id),
                from_chat_id=message.chat_id,
                message_id=message.message_id,
            )
            sent += 1
        except TelegramError as error:
            failed += 1
            logging.warning("Рассылка не доставлена пользователю %s: %s", user_id, error)

    await status_msg.edit_text(
        f"✅ Рассылка завершена!\nУспешно: `{sent}` | Ошибок: `{failed}`",
        parse_mode="Markdown",
    )
    await message.reply_text(
        "Главное меню:",
        reply_markup=main_menu_markup(update.effective_user.id, context),
    )
    return ConversationHandler.END
