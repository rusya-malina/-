"""Выдачи MINTS и стиков, Excel-загрузка и статистика."""
from io import BytesIO
from pathlib import Path

from telegram.error import TelegramError

from application.issuance_service import IssuanceService
from bot_context import (
    ContextTypes,
    ConversationHandler,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    asyncio,
    logging,
    math,
    os,
    pd,
    tempfile,
)
from config import (
    ADMIN_ID,
    ISSUANCE_FILE,
    KPI_FILE,
    USERS_FILE,
)
from data_models import user_name
from errors import StorageError
from keyboards import cancel_keyboard, get_issuance_confirmation_markup, get_issuance_keyboard
from navigation import main_menu_markup
from permissions import Permission, has_permission
from services import (
    _format_quantity,
    _normalize_person_name,
    calculate_balances,
)
from states import (
    ISSUANCE_AMOUNT,
    ISSUANCE_EXCEL_UPLOAD,
    ISSUANCE_MENU,
    ISSUANCE_USER,
)
from storage import load_json


async def _get_issuance_users_markup(context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    users = await load_json(USERS_FILE)
    valid_users = [
        (str(user_id), user_name(name))
        for user_id, name in users.items()
        if str(user_id).isdigit() and user_name(name) and user_name(name).lower() != "nan"
    ]
    valid_users.sort(key=lambda item: item[1].lower())

    keyboard = []
    for user_id, name in valid_users:
        keyboard.append([InlineKeyboardButton(name, callback_data=f"issue_user:{user_id}")])
    keyboard.append([InlineKeyboardButton("⬅️ Отмена", callback_data="issue_cancel")])
    return InlineKeyboardMarkup(keyboard)


async def issuance_menu_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, context, Permission.ISSUANCE):
        await update.message.reply_text("⛔️ У вас нет доступа к этому разделу.")
        return ConversationHandler.END

    action = update.message.text
    if action == "MINTS":
        return await issuance_type_message(update, context, "mints")
    if action == "Стики":
        return await issuance_type_message(update, context, "sticks")
    if action == "📥 Загрузить выдачи (Excel)":
        await update.message.reply_text(
            "📥 **Загрузка выдач из Excel**\n\n"
            "Отправьте файл `.xlsx` с колонками имени сотрудника, MINTS и стиков.\n"
            "Поддерживаются заголовки `full_name`/`ФИО`, `mints`/`mints_issued`/`MINTS` "
            "и `sticks`/`sticks_issued`/`Стики`.\n\n"
            "Значения из файла будут добавлены к текущим выдачам.",
            reply_markup=cancel_keyboard,
            parse_mode="Markdown",
        )
        return ISSUANCE_EXCEL_UPLOAD
    if action == "📊 Выгрузка статистики":
        return await export_issuance_statistics(update, context)
    return ISSUANCE_MENU


async def export_issuance_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, context, Permission.ISSUANCE):
        await update.message.reply_text("⛔️ У вас нет доступа к этому разделу.")
        return ConversationHandler.END

    report_path = None
    try:
        users_data = await load_json(USERS_FILE)
        kpi_data = await load_json(KPI_FILE)
        issuance_data = await load_json(ISSUANCE_FILE)
        rows = []
        for user_id, user_name in sorted(users_data.items(), key=lambda item: str(item[1]).lower()):
            employee_name = str(user_name).strip()
            if not employee_name or employee_name.lower() == "nan":
                continue
            user_kpi = kpi_data.get(_normalize_person_name(employee_name), {})
            balances = calculate_balances(user_kpi, issuance_data.get(str(user_id), {}))
            rows.append(
                {
                    "Сотрудник": employee_name,
                    "Telegram ID": str(user_id) if str(user_id).isdigit() else "",
                    "Выдано MINTS": balances["mints_issued"],
                    "LAS факт": balances["las_done"],
                    "LAU факт": balances["lau_done"],
                    "Списано MINTS": balances["mints_used"],
                    "Остаток MINTS": balances["mints_balance"],
                    "Выдано стиков": balances["sticks_issued"],
                    "ГТ факт": balances["sticks_used"],
                    "Остаток стиков": balances["sticks_balance"],
                }
            )

        report = pd.DataFrame(rows)
        with tempfile.NamedTemporaryFile(prefix="issuance_statistics_", suffix=".xlsx", delete=False) as temp_file:
            report_path = temp_file.name
        await asyncio.to_thread(report.to_excel, report_path, index=False, engine="openpyxl")
        report_bytes = await asyncio.to_thread(Path(report_path).read_bytes)
        await update.message.reply_document(
            document=BytesIO(report_bytes),
            filename="issuance_statistics.xlsx",
            caption="📊 Статистика по выданным и остаточным MINTS/стикам.",
        )
        await update.message.reply_text("📦 Раздел «Выдача»:", reply_markup=get_issuance_keyboard())
        return ISSUANCE_MENU
    except (OSError, KeyError, StorageError, TypeError, ValueError, TelegramError) as error:
        logging.exception("Ошибка формирования статистики выдач: %s", error)
        await update.message.reply_text("❌ Не удалось сформировать статистику.", reply_markup=get_issuance_keyboard())
        return ISSUANCE_MENU
    finally:
        if report_path and os.path.exists(report_path):
            os.remove(report_path)


async def issuance_type_message(update: Update, context: ContextTypes.DEFAULT_TYPE, issuance_type: str):
    if not has_permission(update.effective_user.id, context, Permission.ISSUANCE):
        await update.message.reply_text("⛔️ У вас нет доступа к этому разделу.")
        return ConversationHandler.END

    if issuance_type not in {"mints", "sticks"}:
        await update.message.reply_text("❌ Неизвестный тип выдачи.")
        return ISSUANCE_USER

    context.user_data["issuance_type"] = issuance_type
    type_label = "MINTS" if issuance_type == "mints" else "стиков"
    await update.message.reply_text(
        f"👥 **Выдача {type_label}**\n\nВыберите пользователя:",
        reply_markup=await _get_issuance_users_markup(context),
        parse_mode="Markdown",
    )
    return ISSUANCE_USER


async def start_issuance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, context, Permission.ISSUANCE):
        await update.message.reply_text("⛔️ У вас нет доступа к этой команде.")
        return ConversationHandler.END

    context.user_data.pop("issuance_type", None)
    context.user_data.pop("issuance_user_id", None)
    context.user_data.pop("issuance_amount", None)
    await update.message.reply_text(
        "📦 **Выдача**\n\nВыберите действие:",
        reply_markup=get_issuance_keyboard(),
        parse_mode="Markdown",
    )
    return ISSUANCE_MENU


async def confirm_issuance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = context.user_data.get("issuance_user_id")
    issuance_type = context.user_data.get("issuance_type")
    amount = context.user_data.get("issuance_amount")
    users = await load_json(USERS_FILE)
    user_name_value = user_name(users.get(user_id))

    if not user_id or not issuance_type or not user_name_value or amount is None:
        await query.message.edit_text("❌ Сессия выдачи устарела. Начните операцию заново.")
        context.user_data.pop("issuance_type", None)
        context.user_data.pop("issuance_user_id", None)
        context.user_data.pop("issuance_amount", None)
        return ConversationHandler.END

    result = await IssuanceService.from_default_storage().issue(
        user_id,
        user_name_value,
        issuance_type,
        amount,
        ADMIN_ID,
    )
    if not result.ok:
        await query.message.edit_text("❌ Не удалось сохранить выдачу. Начните операцию заново.")
        return ConversationHandler.END

    total = result.details["total"]
    type_label = "MINTS" if issuance_type == "mints" else "стиков"
    await query.message.edit_text(
        f"✅ Выдано **{_format_quantity(float(amount))} {type_label}** пользователю **{user_name_value}**.\n"
        f"Всего выдано: **{_format_quantity(total)}**.",
        parse_mode="Markdown",
    )
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="🏠 Главное меню:",
        reply_markup=main_menu_markup(ADMIN_ID, context),
    )
    context.user_data.pop("issuance_type", None)
    context.user_data.pop("issuance_user_id", None)
    context.user_data.pop("issuance_amount", None)
    return ConversationHandler.END


async def issuance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not has_permission(query.from_user.id, context, Permission.ISSUANCE):
        await query.message.edit_text("⛔️ У вас нет доступа к этому разделу.")
        return ConversationHandler.END

    data = query.data
    if data == "issue_confirm":
        return await confirm_issuance(update, context)

    if data == "issue_change_user":
        context.user_data.pop("issuance_user_id", None)
        context.user_data.pop("issuance_amount", None)
        issuance_type = context.user_data.get("issuance_type")
        type_label = "MINTS" if issuance_type == "mints" else "стиков"
        await query.message.edit_text(
            f"👥 **Выдача {type_label}**\n\nВыберите пользователя:",
            reply_markup=await _get_issuance_users_markup(context),
            parse_mode="Markdown",
        )
        return ISSUANCE_USER

    if data == "issue_cancel":
        for key in ("issuance_type", "issuance_user_id", "issuance_amount"):
            context.user_data.pop(key, None)
        await query.message.delete()
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ Выдача отменена.",
            reply_markup=main_menu_markup(ADMIN_ID, context),
        )
        return ConversationHandler.END

    if data.startswith("issue_type:"):
        issuance_type = data.split(":", 1)[1]
        if issuance_type not in {"mints", "sticks"}:
            await query.message.edit_text("❌ Неизвестный тип выдачи.")
            return ISSUANCE_USER
        context.user_data["issuance_type"] = issuance_type
        type_label = "MINTS" if issuance_type == "mints" else "стиков"
        await query.message.edit_text(
            f"👥 **Выдача {type_label}**\n\nВыберите пользователя:",
            reply_markup=await _get_issuance_users_markup(context),
            parse_mode="Markdown",
        )
        return ISSUANCE_USER

    if data.startswith("issue_user:"):
        user_id = data.split(":", 1)[1]
        users = await load_json(USERS_FILE)
        user_name_value = user_name(users.get(user_id))
        if not user_id.isdigit() or not user_name_value:
            await query.message.edit_text("❌ Пользователь не найден.")
            return ISSUANCE_USER

        context.user_data["issuance_user_id"] = user_id
        issuance_type = context.user_data.get("issuance_type")
        type_label = "MINTS" if issuance_type == "mints" else "стиков"
        await query.message.edit_text(
            f"👤 Пользователь: **{user_name_value}**\n\nВведите количество {type_label} для выдачи:",
            parse_mode="Markdown",
        )
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Введите число больше нуля или нажмите «Назад».",
            reply_markup=cancel_keyboard,
        )
        return ISSUANCE_AMOUNT

    return ISSUANCE_USER


async def process_issuance_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, context, Permission.ISSUANCE):
        await update.message.reply_text("⛔️ У вас нет доступа к этой команде.")
        return ConversationHandler.END

    raw_amount = update.message.text.strip().replace(",", ".")
    try:
        amount = float(raw_amount)
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число, например `10`.", parse_mode="Markdown")
        return ISSUANCE_AMOUNT

    if not math.isfinite(amount) or amount <= 0:
        await update.message.reply_text("❌ Количество должно быть конечным числом больше нуля.")
        return ISSUANCE_AMOUNT

    user_id = context.user_data.get("issuance_user_id")
    issuance_type = context.user_data.get("issuance_type")
    users = await load_json(USERS_FILE)
    user_name_value = user_name(users.get(user_id))
    if not user_id or not issuance_type or not user_name_value:
        await update.message.reply_text("❌ Сессия выдачи устарела. Начните выдачу заново.", reply_markup=main_menu_markup(ADMIN_ID, context))
        return ConversationHandler.END

    type_label = "MINTS" if issuance_type == "mints" else "стиков"
    context.user_data["issuance_amount"] = amount
    await update.message.reply_text(
        f"🔎 **Проверьте выдачу**\n\n"
        f"Пользователь: **{user_name_value}**\n"
        f"Тип: **{type_label}**\n"
        f"Количество: **{_format_quantity(amount)}**\n\n"
        "Нажмите «Выдать» для записи операции или измените пользователя.",
        reply_markup=get_issuance_confirmation_markup(),
        parse_mode="Markdown",
    )
    return ISSUANCE_AMOUNT
