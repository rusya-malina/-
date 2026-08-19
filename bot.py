import logging
import os
import json
import warnings
import asyncio
import pandas as pd

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.error import BadRequest
from telegram.warnings import PTBUserWarning
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from telegram.request import HTTPXRequest

# === ОТКЛЮЧЕНИЕ ПРЕПЯТСТВУЮЩИХ ПРЕДУПРЕЖДЕНИЙ PTB ===
warnings.filterwarnings("ignore", category=PTBUserWarning)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# === НАСТРОЙКИ ===
TOKEN = os.getenv("BOT_TOKEN", "8768439751:AAFlK2BeYJCbTzqT14zduunQ4ZktDfC50bI")
ADMIN_ID = 14599689
USERS_FILE = "users.json"
KPI_FILE = "kpi_data.json"
PLANS_FILE = "plans_config.json"
PENDING_FILE = "pending_requests.json"

# Состояния разговора
(
    REG_FIRST_NAME,
    REG_LAST_NAME,
    LAS,
    LAU,
    CHANGE_NAME,
    CHANGE_LAST_NAME,
    BROADCAST,
    UPLOAD_EXCEL,
    MANUAL_KPI_NAME,
    SELECT_PREVIOUS_EMP,
    MANUAL_KPI_NEW_NAME,
    MANUAL_KPI_GT_FACT,
    MANUAL_KPI_MICRO_LAS_FACT,
    MANUAL_KPI_MICRO_LAU_FACT,
    MANUAL_KPI_RETRAFIC_FACT,
    MANUAL_KPI_OFFICE_HOURS,
    MANUAL_KPI_FIELD_HOURS,
    SET_PLAN_GT,
    SET_PLAN_MICRO,
    SET_PLAN_RETRAFIC,
    CONFIRM_DELETE_EMP,
    EXTRA_MENU_STATE,
    DELETE_BY_NUM_STATE,
    KPI_MENU_STATE,
    PENDING_REQUESTS_STATE,
) = range(25)


# === ДИНАМИЧЕСКИЕ КЛАВИАТУРЫ ===
def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Формирует главную клавиатуру в зависимости от прав пользователя."""
    keyboard = [
        ["Новый расчет"],
        ["Мой KPI", "Справочник KPI"],
        ["Сменить имя"],
    ]

    if user_id == ADMIN_ID:
        keyboard.append(["Загрузить данные"])
        keyboard.append(["📢 Рассылка", "⚙️ Дополнительно"])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_kpi_menu_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура подменю 'KPI' (только для админа)."""
    keyboard = [
        ["📥 Загрузить KPI (Excel)", "✏️ Ввести KPI вручную"],
        ["⬅️ Назад"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_extra_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура раздела 'Дополнительно' (только для админа)."""
    keyboard = [
        ["👥 Пользователи"],
        ["📥 Заявки на вступление"],
        ["🗑 Удалить по номеру"],
        ["⬅️ Назад"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


cancel_keyboard = ReplyKeyboardMarkup([["⬅️ Назад"]], resize_keyboard=True)


# === АСИНХРОННАЯ РАБОТА С ФАЙЛАМИ И EXCEL (ПРЕДОТВРАЩАЕТ ЗАВИСАНИЯ) ===
def _sync_load_json(filepath: str) -> dict:
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logging.error(f"Ошибка чтения файла {filepath}: {e}")
        return {}


def _sync_save_json(data: dict, filepath: str) -> None:
    temp_file = filepath + ".tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        if os.path.exists(filepath):
            os.remove(filepath)
        os.rename(temp_file, filepath)
    except OSError as e:
        logging.error(f"Ошибка сохранения файла {filepath}: {e}")


async def load_json(filepath: str) -> dict:
    return await asyncio.to_thread(_sync_load_json, filepath)


async def save_json(data: dict, filepath: str) -> None:
    await asyncio.to_thread(_sync_save_json, data, filepath)


async def load_pending() -> dict:
    return await load_json(PENDING_FILE)


async def save_pending(data: dict) -> None:
    await save_json(data, PENDING_FILE)


async def get_default_plans() -> dict:
    plans = await load_json(PLANS_FILE)
    return {
        "gt_plan": plans.get("gt_plan", 90.0),
        "micro_plan": plans.get("micro_plan", 128.0),
        "retrafic_plan": plans.get("retrafic_plan", 15.0),
    }


# === ФОНОВАЯ ПРОВЕРКА ЗАЯВОК (КАЖДЫЕ 5 МИНУТ) ===
async def check_pending_requests_job(context: ContextTypes.DEFAULT_TYPE):
    pending = await load_pending()
    if pending:
        count = len(pending)
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"⏰ **Напоминание:** У вас есть необработанные заявки на вступление (`{count} шт.`).\n"
                    "Зайдите в раздел: **⚙️ Дополнительно ➡️ 📥 Заявки на вступление**."
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logging.error(f"Не удалось отправить напоминание о заявках: {e}")


# === УВЕДОМЛЕНИЯ ПОЛЬЗОВАТЕЛЕЙ ===
async def notify_user_kpi_updated(context: ContextTypes.DEFAULT_TYPE, target_name: str):
    users = await load_json(USERS_FILE)
    clean_target = target_name.strip().lower()

    target_user_id = None
    for uid, u_name in users.items():
        if u_name.strip().lower() == clean_target:
            target_user_id = uid
            break

    if target_user_id and target_user_id.isdigit():
        try:
            await context.bot.send_message(
                chat_id=int(target_user_id),
                text=(
                    "🔔 **Ваши показатели KPI были обновлены!**\n\n"
                    "Нажмите кнопку **«Мой KPI»**, чтобы посмотреть актуальные данные."
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление пользователю {target_user_id}: {e}")


async def notify_user_bot_stopped(context: ContextTypes.DEFAULT_TYPE, user_id: str):
    if user_id and user_id.isdigit():
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text="⛔️ Работа бота остановлена.\nВы были удалены из системы",
                reply_markup=ReplyKeyboardRemove(),
            )
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление об остановке пользователю {user_id}: {e}")


# === ПОДМЕНЮ KPI (ТОЛЬКО АДМИН) ===
async def open_kpi_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ У вас нет доступа к этому разделу.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📊 **Управление KPI**\n\nВыберите способ внесения данных:",
        reply_markup=get_kpi_menu_keyboard(),
        parse_mode="Markdown",
    )
    return KPI_MENU_STATE


# === РАЗДЕЛ ДОПОЛНИТЕЛЬНО (ТОЛЬКО АДМИН) ===
async def open_extra_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ У вас нет доступа к этому разделу.")
        return ConversationHandler.END

    await update.message.reply_text(
        "⚙️ **Раздел «Дополнительно»**\n\nВыберите необходимое действие:",
        reply_markup=get_extra_keyboard(),
        parse_mode="Markdown",
    )
    return EXTRA_MENU_STATE


async def show_registered_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ У вас нет доступа к этой команде.")
        return ConversationHandler.END

    users_data = await load_json(USERS_FILE)

    if not users_data:
        await update.message.reply_text(
            "📋 **Зарегистрированных пользователей нет.**",
            reply_markup=get_extra_keyboard(),
            parse_mode="Markdown",
        )
        return EXTRA_MENU_STATE

    real_users = []
    service_users = []

    for uid, name in users_data.items():
        if uid.isdigit():
            real_users.append((name, uid))
        else:
            service_users.append((name, uid))

    sorted_real = sorted(real_users, key=lambda x: x[0])
    sorted_service = sorted(service_users, key=lambda x: x[0])

    response_text = f"👥 **Список зарегистрированных пользователей ({len(real_users)}):**\n\n"
    user_index_map = {}
    current_index = 1

    if sorted_real:
        for name, uid in sorted_real:
            user_index_map[current_index] = {"uid": uid, "name": name}
            response_text += f"{current_index}. *{name}* (ID: `{uid}`)\n"
            current_index += 1
    else:
        response_text += "_Пользователи еще не проходили регистрацию в боте._\n"

    if sorted_service:
        response_text += f"\n📁 *Имена из файлов/ручного ввода без привязки Telegram ({len(sorted_service)}):*\n"
        for name, uid in sorted_service:
            user_index_map[current_index] = {"uid": uid, "name": name}
            response_text += f"{current_index}. *{name}*\n"
            current_index += 1

    context.user_data["user_index_map"] = user_index_map

    await update.message.reply_text(
        response_text,
        reply_markup=get_extra_keyboard(),
        parse_mode="Markdown",
    )
    return EXTRA_MENU_STATE


# === УПРАВЛЕНИЕ ЗАЯВКАМИ ИЗ РАЗДЕЛА ДОПОЛНИТЕЛЬНО ===
async def show_pending_requests_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ У вас нет доступа к этому разделу.")
        return ConversationHandler.END

    pending = await load_pending()
    if not pending:
        await update.message.reply_text(
            "📂 **Новых заявок на вступление нет.** Все заявки обработаны.",
            reply_markup=get_extra_keyboard(),
            parse_mode="Markdown",
        )
        return EXTRA_MENU_STATE

    inline_keyboard = []
    for uid, name in pending.items():
        inline_keyboard.append([InlineKeyboardButton(f"✅ Одобрить: {name}", callback_data=f"pend_accept:{uid}")])
    
    inline_keyboard.append([InlineKeyboardButton("🔥 Одобрить всех", callback_data="pend_accept_all")])
    inline_keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="pend_back")])

    await update.message.reply_text(
        f"📥 **Список активных заявок ({len(pending)}):**\n\n"
        "Нажмите на имя сотрудника для одобрения или выберите кнопку «Одобрить всех».",
        reply_markup=InlineKeyboardMarkup(inline_keyboard),
        parse_mode="Markdown",
    )
    return PENDING_REQUESTS_STATE


async def pending_requests_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "pend_back":
        await query.message.delete()
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⚙️ Раздел «Дополнительно»:",
            reply_markup=get_extra_keyboard(),
        )
        return EXTRA_MENU_STATE

    pending = await load_pending()

    if data == "pend_accept_all":
        if not pending:
            await query.message.edit_text("⚠️ Список заявок пуст.")
            return EXTRA_MENU_STATE

        users = await load_json(USERS_FILE)
        approved_count = 0

        for uid_str, full_name in list(pending.items()):
            target_id = int(uid_str)
            users[uid_str] = full_name
            approved_count += 1
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=f"🎉 **Ваша заявка одобрена!**\n\nДобро пожаловать, {full_name}!",
                    reply_markup=get_main_keyboard(target_id),
                    parse_mode="Markdown",
                )
            except Exception as e:
                logging.error(f"Не удалось уведомить пользователя {target_id}: {e}")

        await save_json(users, USERS_FILE)
        await save_pending({})

        await query.message.edit_text(
            f"✅ **Все заявки ({approved_count} шт.) успешно одобрены!**",
            parse_mode="Markdown",
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⚙️ Раздел «Дополнительно»:",
            reply_markup=get_extra_keyboard(),
        )
        return EXTRA_MENU_STATE

    if data.startswith("pend_accept:"):
        _, uid_str = data.split(":", 1)
        if uid_str not in pending:
            await query.answer("Эта заявка уже была обработана или удалена.", show_alert=True)
            return PENDING_REQUESTS_STATE

        full_name = pending[uid_str]
        target_id = int(uid_str)

        users = await load_json(USERS_FILE)
        users[uid_str] = full_name
        await save_json(users, USERS_FILE)

        del pending[uid_str]
        await save_pending(pending)

        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"🎉 **Ваша заявка одобрена!**\n\nДобро пожаловать, {full_name}!",
                reply_markup=get_main_keyboard(target_id),
                parse_mode="Markdown",
            )
        except Exception as e:
            logging.error(f"Не удалось уведомить пользователя {target_id}: {e}")

        if not pending:
            await query.message.edit_text(
                f"✅ Заявка пользователя *{full_name}* одобрена. Больше активных заявок нет.",
                parse_mode="Markdown",
            )
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="⚙️ Раздел «Дополнительно»:",
                reply_markup=get_extra_keyboard(),
            )
            return EXTRA_MENU_STATE
        else:
            inline_keyboard = []
            for uid, name in pending.items():
                inline_keyboard.append([InlineKeyboardButton(f"✅ Одобрить: {name}", callback_data=f"pend_accept:{uid}")])
            inline_keyboard.append([InlineKeyboardButton("🔥 Одобрить всех", callback_data="pend_accept_all")])
            inline_keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="pend_back")])

            await query.message.edit_text(
                f"📥 **Список активных заявок ({len(pending)}):**\n\n"
                f"✅ Последняя одобренная: *{full_name}*\n"
                "Выберите следующую заявку:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard),
                parse_mode="Markdown",
            )
            return PENDING_REQUESTS_STATE


# === УДАЛЕНИЕ ПОЛЬЗОВАТЕЛЯ ПО НОМЕРУ ===
async def request_user_number_to_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
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
    target_uid = target_user["uid"]
    target_name = target_user["name"]

    await notify_user_bot_stopped(context, target_uid)

    users_data = await load_json(USERS_FILE)
    if target_uid in users_data:
        del users_data[target_uid]
        await save_json(users_data, USERS_FILE)

    kpi_data = await load_json(KPI_FILE)
    clean_name = target_name.strip().lower()
    if clean_name in kpi_data:
        del kpi_data[clean_name]
        await save_json(kpi_data, KPI_FILE)

    del user_map[num]
    context.user_data["user_index_map"] = user_map

    await update.message.reply_text(
        f"✅ **Пользователь под №{num} (*{target_name}*) успешно удалён!**",
        reply_markup=get_extra_keyboard(),
        parse_mode="Markdown",
    )
    return EXTRA_MENU_STATE


# === ДВУХЭТАПНАЯ РЕГИСТРАЦИЯ И МОДЕРАЦИЯ ===
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


async def admin_moderation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data.startswith("adm_accept:"):
        _, target_id_str, full_name = data.split(":", 2)
        target_id = int(target_id_str)

        users = await load_json(USERS_FILE)
        users[str(target_id)] = full_name
        await save_json(users, USERS_FILE)

        pending = await load_pending()
        if str(target_id) in pending:
            del pending[str(target_id)]
            await save_pending(pending)

        await query.message.edit_text(
            f"✅ **Заявка одобрена.**\nПользователь *{full_name}* успешно зарегистрирован.",
            parse_mode="Markdown",
        )

        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=(
                    f"🎉 **Ваша заявка одобрена!**\n\n"
                    f"Добро пожаловать, {full_name}!"
                ),
                reply_markup=get_main_keyboard(target_id),
                parse_mode="Markdown",
            )
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление пользователю {target_id}: {e}")

    elif data.startswith("adm_reject:"):
        _, target_id_str = data.split(":", 1)
        target_id = int(target_id_str)

        pending = await load_pending()
        if str(target_id) in pending:
            del pending[str(target_id)]
            await save_pending(pending)

        await query.message.edit_text(
            "❌ **Заявка отклонена.**",
            parse_mode="Markdown",
        )

        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="❌ К сожалению, ваша заявка на регистрацию была отклонена администратором.",
                reply_markup=ReplyKeyboardRemove(),
            )
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление об отказе пользователю {target_id}: {e}")


# === СМЕНА ИМЕНИ (В 2 ЭТАПА) ===
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


# === ЗАГРУЗКА EXCEL ДЛЯ АДМИНА ===
async def start_excel_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ У вас нет доступа к этой команде.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📊 **Загрузка данных KPI из Excel**\n\n"
        "Отправьте `.xlsx` файл со следующими столбцами:\n"
        "• `full_name`, `gt_plan`, `gt_fact`, `micro_plan`, `micro_las_fact`, `micro_lau_fact`, `retrafic_plan`, `retrafic_fact`, `office_hours`, `field_hours`",
        reply_markup=cancel_keyboard,
        parse_mode="Markdown",
    )
    return UPLOAD_EXCEL


async def process_excel_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id_num = update.effective_user.id
    document = update.message.document

    if not document.file_name.endswith((".xlsx", ".xls")):
        await update.message.reply_text(
            "⚠️ Пожалуйста, отправьте файл в формате Excel (`.xlsx` или `.xls`).",
            parse_mode="Markdown",
        )
        return UPLOAD_EXCEL

    file_path = "temp_kpi.xlsx"
    file = await context.bot.get_file(document.file_id)
    await file.download_to_drive(file_path)

    try:
        # Асинхронное чтение Excel для избежания фризов бота
        def read_and_clean_excel(path):
            df = pd.read_excel(path)
            required_cols = [
                "full_name", "gt_plan", "gt_fact", "micro_plan", 
                "micro_las_fact", "micro_lau_fact", "retrafic_plan", 
                "retrafic_fact", "office_hours", "field_hours",
            ]
            if not all(col in df.columns for col in required_cols):
                return None
            
            # Заменяем NaN на 0 для числовых столбцов
            numeric_cols = [
                "gt_plan", "gt_fact", "micro_plan", "micro_las_fact", 
                "micro_lau_fact", "retrafic_plan", "retrafic_fact", 
                "office_hours", "field_hours"
            ]
            df[numeric_cols] = df[numeric_cols].fillna(0)
            return df

        df = await asyncio.to_thread(read_and_clean_excel, file_path)

        if df is None:
            await update.message.reply_text(
                "❌ **Ошибка структуры файла! Проверьте обязательные столбцы (включая office_hours и field_hours).**",
                parse_mode="Markdown",
            )
            if os.path.exists(file_path):
                os.remove(file_path)
            return UPLOAD_EXCEL

        kpi_data = await load_json(KPI_FILE)
        users_data = await load_json(USERS_FILE)
        existing_user_names = [v.strip().lower() for v in users_data.values()]
        updated_names = []

        for _, row in df.iterrows():
            emp_name = str(row["full_name"]).strip()
            clean_name = emp_name.lower()
            
            kpi_data[clean_name] = {
                "original_name": emp_name,
                "gt_plan": float(row["gt_plan"]),
                "gt_fact": float(row["gt_fact"]),
                "micro_plan": float(row["micro_plan"]),
                "micro_las_fact": float(row["micro_las_fact"]),
                "micro_lau_fact": float(row["micro_lau_fact"]),
                "retrafic_plan": float(row["retrafic_plan"]),
                "retrafic_fact": float(row["retrafic_fact"]),
                "office_hours": float(row["office_hours"]),
                "field_hours": float(row["field_hours"]),
            }
            updated_names.append(emp_name)

            if clean_name not in existing_user_names:
                fake_uid = f"excel_{clean_name}"
                users_data[fake_uid] = emp_name
                existing_user_names.append(clean_name)

        await save_json(kpi_data, KPI_FILE)
        await save_json(users_data, USERS_FILE)
        if os.path.exists(file_path):
            os.remove(file_path)

        for name in updated_names:
            await notify_user_kpi_updated(context, name)

        await update.message.reply_text(
            f"✅ **Данные KPI успешно загружены!**\nЗаписей обновлено: `{len(df)}`",
            reply_markup=get_main_keyboard(user_id_num),
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    except Exception as e:
        logging.error(f"Ошибка при обработке Excel: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        await update.message.reply_text("❌ **Произошла ошибка при чтении файла.**")
        return UPLOAD_EXCEL


# === ВНЕСТИ ПЛАН ===
async def set_plan_gt_start(query, context):
    plans = await get_default_plans()
    await query.message.delete()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=(
            f"🎯 **Настройка общих планов**\n\n"
            f"1️⃣ Введите общий план по **GT** (текущий: `{plans['gt_plan']:.0f}`):"
        ),
        reply_markup=cancel_keyboard,
        parse_mode="Markdown",
    )
    return SET_PLAN_GT


async def set_plan_gt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = parse_single_float(update.message.text)
    if val is None:
        await update.message.reply_text("❌ Ошибка. Введите положительное число для плана GT:")
        return SET_PLAN_GT

    context.user_data["new_plan_gt"] = val
    plans = await get_default_plans()
    await update.message.reply_text(
        f"2️⃣ Введите общий план по **Микроактам** (текущий: `{plans['micro_plan']:.0f}`):",
        reply_markup=cancel_keyboard,
        parse_mode="Markdown",
    )
    return SET_PLAN_MICRO


async def set_plan_micro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = parse_single_float(update.message.text)
    if val is None:
        await update.message.reply_text("❌ Ошибка. Введите положительное число для Микроактов:")
        return SET_PLAN_MICRO

    context.user_data["new_plan_micro"] = val
    plans = await get_default_plans()
    await update.message.reply_text(
        f"3️⃣ Введите общий план по **Re-trafic** (текущий: `{plans['retrafic_plan']:.0f}`):",
        reply_markup=cancel_keyboard,
        parse_mode="Markdown",
    )
    return SET_PLAN_RETRAFIC


async def set_plan_retrafic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = parse_single_float(update.message.text)
    user_id_num = update.effective_user.id
    if val is None:
        await update.message.reply_text("❌ Ошибка. Введите положительное число для Re-trafic:")
        return SET_PLAN_RETRAFIC

    plans = {
        "gt_plan": context.user_data["new_plan_gt"],
        "micro_plan": context.user_data["new_plan_micro"],
        "retrafic_plan": val,
    }
    await save_json(plans, PLANS_FILE)

    await update.message.reply_text(
        "✅ **Общие планы успешно обновлены!**",
        reply_markup=get_main_keyboard(user_id_num),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


# === РУЧНОЙ ВВОД KPI ===
async def get_manual_kpi_inline_markup() -> InlineKeyboardMarkup:
    kpi_data = await load_json(KPI_FILE)
    inline_keyboard = []

    if kpi_data:
        inline_keyboard.append([InlineKeyboardButton("📋 Ранее добавленные", callback_data="manual_emp_prev")])

    inline_keyboard.append([InlineKeyboardButton("➕ Новый сотрудник", callback_data="manual_emp_new")])
    if kpi_data:
        inline_keyboard.append([InlineKeyboardButton("🗑 Удалить сотрудника", callback_data="manual_emp_del_menu")])
    inline_keyboard.append([InlineKeyboardButton("⚙️ Внести общий план", callback_data="manual_emp_plan")])
    inline_keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="manual_emp_cancel")])

    return InlineKeyboardMarkup(inline_keyboard)


async def start_manual_kpi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ У вас нет доступа к этой команде.")
        return ConversationHandler.END

    markup = await get_manual_kpi_inline_markup()
    await update.message.reply_text(
        "✏️ **Ручной ввод / Редактирование KPI**\n\nВыберите нужное действие:",
        reply_markup=markup,
        parse_mode="Markdown",
    )
    return MANUAL_KPI_NAME


async def go_back_to_manual_menu(query):
    markup = await get_manual_kpi_inline_markup()
    await query.message.edit_text(
        "✏️ **Ручной ввод / Редактирование KPI**\n\nВыберите нужное действие:",
        reply_markup=markup,
        parse_mode="Markdown",
    )
    return MANUAL_KPI_NAME


def show_delete_menu(kpi_data):
    inline_keyboard = []
    if kpi_data:
        names = sorted([info["original_name"] for info in kpi_data.values()])
        row = []
        for name in names:
            row.append(InlineKeyboardButton(f"❌ {name}", callback_data=f"del_select:{name}"))
            if len(row) == 2:
                inline_keyboard.append(row)
                row = []
        if row:
            inline_keyboard.append(row)

    inline_keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="manual_emp_back")])
    return InlineKeyboardMarkup(inline_keyboard)


async def manual_kpi_select_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "manual_emp_cancel":
        await query.message.delete()
        user_id_num = query.from_user.id
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ Действие отменено.",
            reply_markup=get_main_keyboard(user_id_num),
        )
        return ConversationHandler.END

    if data == "manual_emp_plan":
        return await set_plan_gt_start(query, context)

    if data == "manual_emp_new":
        await query.message.edit_text(
            "👤 Введите **Имя и Фамилию** нового сотрудника:",
            parse_mode="Markdown",
        )
        return MANUAL_KPI_NEW_NAME

    if data == "manual_emp_prev":
        kpi_data = await load_json(KPI_FILE)
        inline_keyboard = []
        if kpi_data:
            names = sorted([info["original_name"] for info in kpi_data.values()])
            row = []
            for name in names:
                row.append(InlineKeyboardButton(name, callback_data=f"sel_emp:{name}"))
                if len(row) == 2:
                    inline_keyboard.append(row)
                    row = []
            if row:
                inline_keyboard.append(row)

        inline_keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="manual_emp_back")])

        await query.message.edit_text(
            "📋 **Ранее добавленные сотрудники**\n\nВыберите сотрудника:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard),
            parse_mode="Markdown",
        )
        return SELECT_PREVIOUS_EMP

    if data == "manual_emp_del_menu":
        kpi_data = await load_json(KPI_FILE)
        markup = show_delete_menu(kpi_data)
        await query.message.edit_text(
            "🗑 **Удаление сотрудника из системы**",
            reply_markup=markup,
            parse_mode="Markdown",
        )
        return CONFIRM_DELETE_EMP


async def select_previous_employee_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "manual_emp_back":
        return await go_back_to_manual_menu(query)

    if data == "manual_emp_cancel":
        await query.message.delete()
        user_id_num = query.from_user.id
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ Действие отменено.",
            reply_markup=get_main_keyboard(user_id_num),
        )
        return ConversationHandler.END

    if data.startswith("sel_emp:"):
        target_name = data.split("sel_emp:", 1)[1]
        context.user_data["manual_kpi_name"] = target_name

        await query.message.edit_text(
            f"👤 Выбран сотрудник: *{target_name}*\n\n1️⃣ Введите **ФАКТ GT**:",
            parse_mode="Markdown",
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Для отмены используйте кнопку ниже:",
            reply_markup=cancel_keyboard,
        )
        return MANUAL_KPI_GT_FACT


async def delete_employee_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id_num = query.from_user.id

    if data == "del_back_list":
        kpi_data = await load_json(KPI_FILE)
        markup = show_delete_menu(kpi_data)
        await query.message.edit_text(
            "🗑 **Удаление сотрудника**",
            reply_markup=markup,
            parse_mode="Markdown",
        )
        return CONFIRM_DELETE_EMP

    if data == "manual_emp_back":
        return await go_back_to_manual_menu(query)

    if data == "manual_emp_cancel":
        await query.message.delete()
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ Действие отменено.",
            reply_markup=get_main_keyboard(user_id_num),
        )
        return ConversationHandler.END

    if data.startswith("del_select:"):
        target_name = data.split("del_select:", 1)[1]
        inline_keyboard = [
            [
                InlineKeyboardButton("❌ Удалить из списка", callback_data=f"del_type:list:{target_name}"),
                InlineKeyboardButton("🔥 Удалить полностью", callback_data=f"del_type:full:{target_name}"),
            ],
            [InlineKeyboardButton("⬅️ Назад", callback_data="del_back_list")],
        ]
        await query.message.edit_text(
            f"❓ **Выберите тип удаления для:** *{target_name}*",
            reply_markup=InlineKeyboardMarkup(inline_keyboard),
            parse_mode="Markdown",
        )
        return CONFIRM_DELETE_EMP

    if data.startswith("del_type:"):
        _, del_type, target_name = data.split(":", 2)
        clean_name = target_name.strip().lower()

        kpi_data = await load_json(KPI_FILE)
        if clean_name in kpi_data:
            del kpi_data[clean_name]
            await save_json(kpi_data, KPI_FILE)

        status_text = f"🗑 **Сотрудник {target_name} удалён из списка KPI.**"

        if del_type == "full":
            users_data = await load_json(USERS_FILE)
            to_delete = []
            for uid, name in users_data.items():
                if name.strip().lower() == clean_name:
                    to_delete.append(uid)

            for uid in to_delete:
                await notify_user_bot_stopped(context, uid)
                del users_data[uid]

            await save_json(users_data, USERS_FILE)
            status_text = f"🔥 **Сотрудник {target_name} полностью удалён!**"

        await query.message.delete()
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=status_text,
            reply_markup=get_main_keyboard(user_id_num),
            parse_mode="Markdown",
        )
        return ConversationHandler.END


async def manual_kpi_get_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_name = update.message.text.strip()
    if len(target_name) < 3 or len(target_name.split()) < 2:
        await update.message.reply_text("⚠️ Введите корректные Имя и Фамилию:")
        return MANUAL_KPI_NEW_NAME

    context.user_data["manual_kpi_name"] = target_name
    await update.message.reply_text(
        f"👤 Сотрудник: *{target_name}*\n\n1️⃣ Введите **ФАКТ GT**:",
        reply_markup=cancel_keyboard,
        parse_mode="Markdown",
    )
    return MANUAL_KPI_GT_FACT


def parse_single_float(text: str):
    try:
        val = float(text.replace(",", ".").strip())
        return val if val >= 0 else None
    except ValueError:
        return None


async def manual_kpi_get_gt_fact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = parse_single_float(update.message.text)
    if val is None:
        await update.message.reply_text("❌ Ошибка ввода. Введите положительное число:")
        return MANUAL_KPI_GT_FACT

    context.user_data["manual_gt_fact"] = val
    await update.message.reply_text("2️⃣ Введите **ФАКТ Микроакты LAS**:", reply_markup=cancel_keyboard)
    return MANUAL_KPI_MICRO_LAS_FACT


async def manual_kpi_get_micro_las_fact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = parse_single_float(update.message.text)
    if val is None:
        await update.message.reply_text("❌ Ошибка ввода:")
        return MANUAL_KPI_MICRO_LAS_FACT

    context.user_data["manual_micro_las_fact"] = val
    await update.message.reply_text("3️⃣ Введите **ФАКТ Микроакты LAU**:", reply_markup=cancel_keyboard)
    return MANUAL_KPI_MICRO_LAU_FACT


async def manual_kpi_get_micro_lau_fact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = parse_single_float(update.message.text)
    if val is None:
        await update.message.reply_text("❌ Ошибка ввода:")
        return MANUAL_KPI_MICRO_LAU_FACT

    context.user_data["manual_micro_lau_fact"] = val
    await update.message.reply_text("4️⃣ Введите **ФАКТ Re-trafic**:", reply_markup=cancel_keyboard)
    return MANUAL_KPI_RETRAFIC_FACT


async def manual_kpi_get_retrafic_fact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = parse_single_float(update.message.text)
    if val is None:
        await update.message.reply_text("❌ Ошибка ввода:")
        return MANUAL_KPI_RETRAFIC_FACT

    context.user_data["manual_retrafic_fact"] = val
    await update.message.reply_text("5️⃣ Введите **Офисные часы**:", reply_markup=cancel_keyboard)
    return MANUAL_KPI_OFFICE_HOURS


async def manual_kpi_get_office_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = parse_single_float(update.message.text)
    if val is None:
        await update.message.reply_text("❌ Ошибка ввода:")
        return MANUAL_KPI_OFFICE_HOURS

    context.user_data["manual_office_hours"] = val
    await update.message.reply_text("6️⃣ Введите **Полевые часы**:", reply_markup=cancel_keyboard)
    return MANUAL_KPI_FIELD_HOURS


async def manual_kpi_get_field_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = parse_single_float(update.message.text)
    user_id_num = update.effective_user.id

    if val is None:
        await update.message.reply_text("❌ Ошибка ввода:")
        return MANUAL_KPI_FIELD_HOURS

    field_hours = val
    office_hours = context.user_data["manual_office_hours"]
    retrafic_fact = context.user_data["manual_retrafic_fact"]
    las_fact = context.user_data["manual_micro_las_fact"]
    lau_fact = context.user_data["manual_micro_lau_fact"]
    gt_fact = context.user_data["manual_gt_fact"]
    target_name = context.user_data["manual_kpi_name"]
    clean_name = target_name.strip().lower()

    plans = await get_default_plans()
    kpi_data = await load_json(KPI_FILE)

    existing_user_data = kpi_data.get(clean_name, {})
    gt_plan = existing_user_data.get("gt_plan", plans["gt_plan"])
    micro_plan = existing_user_data.get("micro_plan", plans["micro_plan"])
    retrafic_plan = existing_user_data.get("retrafic_plan", plans["retrafic_plan"])

    kpi_data[clean_name] = {
        "original_name": target_name,
        "gt_plan": gt_plan,
        "gt_fact": gt_fact,
        "micro_plan": micro_plan,
        "micro_las_fact": las_fact,
        "micro_lau_fact": lau_fact,
        "retrafic_plan": retrafic_plan,
        "retrafic_fact": retrafic_fact,
        "office_hours": office_hours,
        "field_hours": field_hours,
    }

    await save_json(kpi_data, KPI_FILE)
    await notify_user_kpi_updated(context, target_name)

    await update.message.reply_text(
        f"✅ **KPI успешно сохранены для {target_name}!**",
        reply_markup=get_main_keyboard(user_id_num),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


# === РАЗДЕЛ МОЙ KPI (С ПОДМЕНЮ) ===
async def my_kpi_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id_num = update.effective_user.id
    user_id = str(user_id_num)
    users = await load_json(USERS_FILE)

    if user_id not in users:
        await update.message.reply_text("⚠️ Вы еще не зарегистрированы. Нажмите /start.")
        return

    inline_keyboard = [
        [InlineKeyboardButton("📊 KPI", callback_data="my_kpi_show_kpi")],
        [InlineKeyboardButton("⏱️ Часы", callback_data="my_kpi_show_hours")],
    ]
    await update.message.reply_text(
        "📌 **Раздел «Мой KPI»**\n\nВыберите интересующий раздел:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard),
        parse_mode="Markdown",
    )


async def my_kpi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id_num = query.from_user.id
    user_id = str(user_id_num)
    users = await load_json(USERS_FILE)
    user_name = users.get(user_id, "")
    lookup_name = user_name.strip().lower()
    kpi_data = await load_json(KPI_FILE)

    if lookup_name not in kpi_data:
        await query.message.edit_text("ℹ️ **Информация по вашим данным не найдена.**", parse_mode="Markdown")
        return

    user_kpi = kpi_data[lookup_name]

    if data == "my_kpi_show_kpi":
        def calc_pct(fact, plan):
            return (fact / plan * 100) if plan > 0 else 0

        las_fact = user_kpi.get("micro_las_fact", 0)
        lau_fact = user_kpi.get("micro_lau_fact", 0)
        micro_fact = las_fact + lau_fact
        micro_plan = user_kpi.get("micro_plan", 0)

        gt_pct = calc_pct(user_kpi["gt_fact"], user_kpi["gt_plan"])
        micro_pct = calc_pct(micro_fact, micro_plan)
        retrafic_pct = calc_pct(user_kpi["retrafic_fact"], user_kpi["retrafic_plan"])

        # Расчет трешхолда LAS %
        las_percent = (las_fact / micro_fact * 100) if micro_fact > 0 else 0
        need_las = 0 if las_percent >= 40 else max(0, int(((0.4 * micro_fact) - las_fact) / 0.6) + 1)

        micro_details = (
            f"🎯 **Микроакты:** План: `{micro_plan:.0f}` | Факт: `{micro_fact:.0f}` (`{micro_pct:.1f}%`)\n"
            f"  ├ Факт LAS: `{las_fact:.0f}` | Факт LAU: `{lau_fact:.0f}`\n"
            f"  ├ Итоговый LAS %: `{las_percent:.2f}%`\n"
        )
        if need_las > 0:
            micro_details += f"  └ ⚠️ **Рекомендация:** Добавить LAS: `{need_las}`\n"
        else:
            micro_details += f"  └ ✅ **Показатель LAS в норме!**\n"

        text = (
            f"📊 **Ваши показатели KPI**\n"
            f"👤 Сотрудник: *{user_name}*\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"📈 **GT:** План: `{user_kpi['gt_plan']:.0f}` | Факт: `{user_kpi['gt_fact']:.0f}` (`{gt_pct:.1f}%`)\n\n"
            f"{micro_details}\n"
            f"🔄 **Re-trafic:** План: `{user_kpi['retrafic_plan']:.0f}` | Факт: `{user_kpi['retrafic_fact']:.0f}` (`{retrafic_pct:.1f}%`)\n"
        )
        inline_keyboard = [[InlineKeyboardButton("⬅️ Назад к меню", callback_data="my_kpi_back")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard), parse_mode="Markdown")

    elif data == "my_kpi_show_hours":
        office_hours = user_kpi.get("office_hours", 0)
        field_hours = user_kpi.get("field_hours", 0)

        text = (
            f"⏱️ **Учет рабочего времени**\n"
            f"👤 Сотрудник: *{user_name}*\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🏢 **Офисные часы:** `{office_hours:.1f}`\n"
            f"⛺️ **Полевые часы:** `{field_hours:.1f}` из 64 часов\n"
        )
        inline_keyboard = [[InlineKeyboardButton("⬅️ Назад к меню", callback_data="my_kpi_back")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard), parse_mode="Markdown")

    elif data == "my_kpi_back":
        inline_keyboard = [
            [InlineKeyboardButton("📊 KPI", callback_data="my_kpi_show_kpi")],
            [InlineKeyboardButton("⏱️ Часы", callback_data="my_kpi_show_hours")],
        ]
        await query.message.edit_text(
            "📌 **Раздел «Мой KPI»**\n\nВыберите интересующий раздел:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard),
            parse_mode="Markdown",
        )


# === СПРАВОЧНИК KPI ===
async def kpi_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inline_keyboard = [
        [InlineKeyboardButton("📈 GT", callback_data="kpi_gt")],
        [InlineKeyboardButton("🎯 Микроакты", callback_data="kpi_microacts")],
        [InlineKeyboardButton("🔄 Re-trafic", callback_data="kpi_retrafic")],
        [InlineKeyboardButton("🔙 Закрыть меню", callback_data="kpi_close")],
    ]
    await update.message.reply_text("Убираем клавиатуру...", reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text("📌 **Выберите KPI:**", reply_markup=InlineKeyboardMarkup(inline_keyboard), parse_mode="Markdown")


async def kpi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id_num = query.from_user.id
    await query.answer()
    data = query.data

    if data == "kpi_gt":
        text = "📈 **KPI: GT** (План: 90, Вес: 40%)"
    elif data == "kpi_microacts":
        text = "🎯 **KPI: Микроакты** (План: 128, Вес: 40%, Трешхолд LAS ≥ 40%)"
    elif data == "kpi_retrafic":
        text = "🔄 **KPI: Re-trafic** (План: 15, Вес: 20%)"
    elif data == "kpi_close":
        await query.message.delete()
        await context.bot.send_message(chat_id=query.message.chat_id, text="🏠 Главное меню:", reply_markup=get_main_keyboard(user_id_num))
        return

    try:
        await query.message.edit_text(text, reply_markup=query.message.reply_markup, parse_mode="Markdown")
    except BadRequest:
        pass


# === РАСЧЕТЫ (LAS / LAU) ===
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
    await update.message.reply_text("❌ Действие отменено.", reply_markup=get_main_keyboard(update.effective_user.id))
    return ConversationHandler.END


# === РАССЫЛКА ===
async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ У вас нет доступа.")
        return ConversationHandler.END

    await update.message.reply_text("📢 Отправьте фото с подписью для рассылки:", reply_markup=cancel_keyboard)
    return BROADCAST


async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("⚠️ Отправьте фотографию.")
        return BROADCAST

    photo_id = update.message.photo[-1].file_id
    caption = update.message.caption or ""
    users = await load_json(USERS_FILE)
    sent, failed = 0, 0

    status_msg = await update.message.reply_text("⏳ Идет рассылка...")

    for user_id in users.keys():
        if not user_id.isdigit(): continue
        try:
            await context.bot.send_photo(chat_id=int(user_id), photo=photo_id, caption=caption)
            sent += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(f"✅ Рассылка завершена!\nУспешно: `{sent}` | Ошибок: `{failed}`", parse_mode="Markdown")
    await update.message.reply_text("Главное меню:", reply_markup=get_main_keyboard(update.effective_user.id))
    return ConversationHandler.END


# === MAIN ===
def main():
    # Настраиваем таймауты сетевых запросов, чтобы бот не зависал при проблемах с сетью
    request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    app = Application.builder().token(TOKEN).request(request).build()

    if app.job_queue:
        app.job_queue.run_repeating(check_pending_requests_job, interval=300, first=60)

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex(r"^Новый расчет$"), new_calculation),
            MessageHandler(filters.Regex(r"^Сменить имя$"), change_name),
            MessageHandler(filters.Regex(r"^📢 Рассылка$"), start_broadcast),
            MessageHandler(filters.Regex(r"^Загрузить данные$"), open_kpi_admin_menu),
            MessageHandler(filters.Regex(r"^⚙️ Дополнительно$"), open_extra_menu),
        ],
        states={
            REG_FIRST_NAME: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, reg_get_first_name),
            ],
            REG_LAST_NAME: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, reg_get_last_name),
            ],
            LAS: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_las),
            ],
            LAU: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_lau),
            ],
            CHANGE_NAME: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_first_name),
            ],
            CHANGE_LAST_NAME: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_full_name),
            ],
            BROADCAST: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.PHOTO, send_broadcast),
            ],
            KPI_MENU_STATE: [
                MessageHandler(filters.Regex(r"^📥 Загрузить KPI \(Excel\)$"), start_excel_upload),
                MessageHandler(filters.Regex(r"^✏️ Ввести KPI вручную$"), start_manual_kpi),
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
            ],
            UPLOAD_EXCEL: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.Document.ALL, process_excel_file),
            ],
            MANUAL_KPI_NAME: [
                CallbackQueryHandler(manual_kpi_select_employee, pattern=r"^manual_emp_"),
            ],
            SELECT_PREVIOUS_EMP: [
                CallbackQueryHandler(select_previous_employee_handler, pattern=r"^(sel_emp:|manual_emp_)"),
            ],
            CONFIRM_DELETE_EMP: [
                CallbackQueryHandler(delete_employee_confirm, pattern=r"^(del_select:|del_type:|del_back_list|manual_emp_)"),
            ],
            MANUAL_KPI_NEW_NAME: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual_kpi_get_new_name),
            ],
            MANUAL_KPI_GT_FACT: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual_kpi_get_gt_fact),
            ],
            MANUAL_KPI_MICRO_LAS_FACT: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual_kpi_get_micro_las_fact),
            ],
            MANUAL_KPI_MICRO_LAU_FACT: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual_kpi_get_micro_lau_fact),
            ],
            MANUAL_KPI_RETRAFIC_FACT: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual_kpi_get_retrafic_fact),
            ],
            MANUAL_KPI_OFFICE_HOURS: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual_kpi_get_office_hours),
            ],
            MANUAL_KPI_FIELD_HOURS: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, manual_kpi_get_field_hours),
            ],
            SET_PLAN_GT: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_plan_gt),
            ],
            SET_PLAN_MICRO: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_plan_micro),
            ],
            SET_PLAN_RETRAFIC: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_plan_retrafic),
            ],
            EXTRA_MENU_STATE: [
                MessageHandler(filters.Regex(r"^👥 Пользователи$"), show_registered_users),
                MessageHandler(filters.Regex(r"^📥 Заявки на вступление$"), show_pending_requests_menu),
                MessageHandler(filters.Regex(r"^🗑 Удалить по номеру$"), request_user_number_to_delete),
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
            ],
            DELETE_BY_NUM_STATE: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_delete_user_by_number),
            ],
            PENDING_REQUESTS_STATE: [
                CallbackQueryHandler(pending_requests_callback, pattern=r"^(pend_accept:|pend_accept_all|pend_back)$"),
            ],
        },
        fallbacks=[MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action)],
        per_chat=True,
        per_user=True,
        per_message=False,
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(admin_moderation_callback, pattern=r"^adm_(accept|reject):"))
    app.add_handler(MessageHandler(filters.Regex(r"^Мой KPI$"), my_kpi_menu))
    app.add_handler(CallbackQueryHandler(my_kpi_callback, pattern=r"^my_kpi_"))
    app.add_handler(MessageHandler(filters.Regex(r"^Справочник KPI$"), kpi_menu))
    app.add_handler(CallbackQueryHandler(kpi_callback, pattern=r"^kpi_"))

    print("🚀 Бот успешно запущен и оптимизирован!")
    app.run_polling()


if __name__ == "__main__":
    main()