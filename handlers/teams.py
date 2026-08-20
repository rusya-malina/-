"""Выбор команды сотрудником и административное подтверждение."""
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
    ISSUANCE_FILE,
    KPI_FILE,
    TEAM_OPTIONS,
    TEAM_REQUESTS_FILE,
    TEAMS_FILE,
    USERS_FILE,
)
from data_models import make_team_record, team_request, user_name
from keyboards import (
    get_main_keyboard,
    get_team_keyboard,
    get_team_menu_keyboard,
)
from organization import (
    get_visible_users,
    is_management_group,
    merge_employee_issuance,
)
from permissions import Permission, has_permission, is_admin_mode
from roles import get_user_group
from services import _format_quantity, _normalize_person_name, calculate_balances
from states import (
    TEAM_MENU_STATE,
    TEAM_SELECTION,
)
from storage import load_json, update_json, update_many_json


async def _get_team_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    group = await get_user_group(user_id)
    admin_mode = is_admin_mode(user_id, context)
    if admin_mode:
        group = "MNG"
    if not is_management_group(group):
        await update.message.reply_text(
            "⛔️ Раздел «Моя команда» доступен только MNG, SPV, coor A и coor R.",
            reply_markup=get_main_keyboard(user_id, group),
        )
        return None

    users = await load_json(USERS_FILE)
    groups = await load_json(GROUPS_FILE)
    kpi_data = await load_json(KPI_FILE)
    issuance_data = await load_json(ISSUANCE_FILE)
    visible_users = get_visible_users(
        user_id,
        users,
        groups,
        admin_mode=admin_mode,
        exclude_user_id=user_id,
        kpi_data=kpi_data,
        issuance_data=issuance_data,
    )
    return user_id, group, visible_users, kpi_data, issuance_data


async def open_my_team_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    team_context = await _get_team_context(update, context)
    if team_context is None:
        return ConversationHandler.END
    await update.message.reply_text(
        "👥 **Моя команда**\n\nВыберите, что показать:",
        reply_markup=get_team_menu_keyboard(),
        parse_mode="Markdown",
    )
    return TEAM_MENU_STATE


def _report_sections(group: str, visible_users: list[dict]) -> list[tuple[str | None, list[dict]]]:
    """MNG/SPV получают две ветки; coor получает свою единую ветку."""
    if group in {"MNG", "SPV"}:
        return [
            (team, [person for person in visible_users if person["group"] == team])
            for team in ("A LAMP", "R LAMP")
        ]
    return [(None, visible_users)]


async def show_team_kpi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    team_context = await _get_team_context(update, context)
    if team_context is None:
        return ConversationHandler.END
    user_id, group, visible_users, kpi_data, _issuance_data = team_context
    title = "MNG" if is_admin_mode(user_id, context) else group
    report_sections = _report_sections(group, visible_users)
    report_users = [person for _section, section_users in report_sections for person in section_users]
    lines = [
        f"📊 **KPI команды — {title}**",
        f"👤 Сотрудников в командах: **{len(report_users)}**\n",
    ]
    for section_name, section_users in report_sections:
        if section_name:
            lines.append(f"🏷 **{section_name}** — сотрудников: **{len(section_users)}**")
        if not section_users:
            lines.append("_Нет зарегистрированных пользователей._\n")
            continue
        for index, person in enumerate(section_users, start=1):
            kpi = kpi_data.get(person.get("name_key") or _normalize_person_name(person["name"]), {})
            gt_plan = float(kpi.get("gt_plan", 0) or 0)
            gt_fact = float(kpi.get("gt_fact", 0) or 0)
            micro_plan = float(kpi.get("micro_plan", 0) or 0)
            micro_fact = float(kpi.get("micro_las_fact", 0) or 0) + float(kpi.get("micro_lau_fact", 0) or 0)
            retrafic_plan = float(kpi.get("retrafic_plan", 0) or 0)
            retrafic_fact = float(kpi.get("retrafic_fact", 0) or 0)
            gt_percent = (gt_fact / gt_plan * 100) if gt_plan else 0
            micro_percent = (micro_fact / micro_plan * 100) if micro_plan else 0
            retrafic_percent = (retrafic_fact / retrafic_plan * 100) if retrafic_plan else 0
            lines.append(
                f"{index}. *{person['name']}* — {person['group']}\n"
                f"   GT: {gt_percent:.0f}% | Микроакты: {micro_percent:.0f}% | Re-trafic: {retrafic_percent:.0f}%"
            )
        lines.append("")
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=get_team_menu_keyboard(),
        parse_mode="Markdown",
    )
    return TEAM_MENU_STATE


async def show_team_balances(update: Update, context: ContextTypes.DEFAULT_TYPE):
    team_context = await _get_team_context(update, context)
    if team_context is None:
        return ConversationHandler.END
    user_id, group, visible_users, kpi_data, issuance_data = team_context
    title = "MNG" if is_admin_mode(user_id, context) else group
    report_sections = _report_sections(group, visible_users)
    report_users = [person for _section, section_users in report_sections for person in section_users]
    lines = [
        f"📦 **Остатки команды — {title}**",
        f"👤 Сотрудников в командах: **{len(report_users)}**\n",
    ]
    for section_name, section_users in report_sections:
        if section_name:
            lines.append(f"🏷 **{section_name}** — сотрудников: **{len(section_users)}**")
        if not section_users:
            lines.append("_Нет зарегистрированных пользователей._\n")
            continue
        for index, person in enumerate(section_users, start=1):
            kpi = kpi_data.get(person.get("name_key") or _normalize_person_name(person["name"]), {})
            balances = calculate_balances(kpi, merge_employee_issuance(person, issuance_data))
            lines.append(
                f"{index}. *{person['name']}* — {person['group']}\n"
                f"   Остаток MINTS: {_format_quantity(balances['mints_balance'])} | "
                f"стиков: {_format_quantity(balances['sticks_balance'])}"
            )
        lines.append("")
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=get_team_menu_keyboard(),
        parse_mode="Markdown",
    )
    return TEAM_MENU_STATE


async def start_team_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users = await load_json(USERS_FILE)
    if (update.effective_user.id == ADMIN_ID and not is_admin_mode(update.effective_user.id, context)) or (user_id not in users and update.effective_user.id != ADMIN_ID):
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
    if update.effective_user.id == ADMIN_ID and not is_admin_mode(update.effective_user.id, context):
        await update.message.reply_text("⛔️ Сначала включите административный режим командой /admin.")
        return ConversationHandler.END
    selected_team = update.message.text.strip()
    if selected_team not in TEAM_OPTIONS:
        await update.message.reply_text("⚠️ Выберите команду кнопкой из списка.", reply_markup=get_team_keyboard())
        return TEAM_SELECTION

    users = await load_json(USERS_FILE)
    user_name_value = user_name(users.get(user_id), "Руслан Малинин" if update.effective_user.id == ADMIN_ID else "")
    if not user_name_value:
        await update.message.reply_text("⚠️ Пользователь ещё не зарегистрирован.", reply_markup=get_main_keyboard(update.effective_user.id))
        return ConversationHandler.END

    request_record = team_request({"user_id": user_id, "name": user_name_value, "team": selected_team}, user_id=user_id)

    def save_request(data: dict) -> None:
        data[user_id] = request_record

    await update_json(TEAM_REQUESTS_FILE, save_request)

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
                f"👤 Сотрудник: *{user_name_value}*\n"
                f"🆔 Telegram ID: `{user_id}`\n"
                f"👥 Команда: **{selected_team}**"
            ),
            reply_markup=InlineKeyboardMarkup(inline_keyboard),
            parse_mode="Markdown",
        )
    except TelegramError as error:
        logging.error("Не удалось отправить запрос команды администратору: %s", error)

    return ConversationHandler.END


async def team_moderation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not has_permission(query.from_user.id, context, Permission.TEAM_APPROVAL):
        await query.message.edit_text("⛔️ У вас нет доступа к этому запросу.")
        return ConversationHandler.END

    action, user_id = query.data.split(":", 1)
    team_requests = await load_json(TEAM_REQUESTS_FILE)
    request = team_requests.get(user_id)
    if not request:
        await query.message.edit_text("ℹ️ Запрос уже обработан или устарел.")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="🏠 Главное меню администратора:",
            reply_markup=get_main_keyboard(ADMIN_ID, admin_mode=True),
        )
        return ConversationHandler.END

    canonical_request = team_request(request, user_id=user_id)
    selected_team = canonical_request["team"]
    user_name_value = user_name(canonical_request)
    if action == "team_accept":
        def accept_team(files: dict[str, dict]) -> None:
            files[TEAMS_FILE][user_id] = make_team_record(user_name_value, selected_team)
            files[TEAM_REQUESTS_FILE].pop(user_id, None)

        await update_many_json((TEAMS_FILE, TEAM_REQUESTS_FILE), accept_team)
        await query.message.edit_text(
            f"✅ **Команда подтверждена**\n\n{user_name_value} → **{selected_team}**",
            parse_mode="Markdown",
        )
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text=f"✅ Администратор подтвердил вашу команду: **{selected_team}**.",
                reply_markup=get_main_keyboard(int(user_id), selected_team),
                parse_mode="Markdown",
            )
        except TelegramError as error:
            logging.error("Не удалось уведомить пользователя о команде: %s", error)
    elif action == "team_reject":
        def reject_team(data: dict) -> None:
            data.pop(user_id, None)

        await update_json(TEAM_REQUESTS_FILE, reject_team)
        await query.message.edit_text(
            f"❌ **Запрос на команду отклонён**\n\n{user_name_value} → **{selected_team}**",
            parse_mode="Markdown",
        )
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text="❌ Запрос на выбранную команду отклонён администратором. Выберите новую группу через /start.",
                reply_markup=get_main_keyboard(int(user_id)),
            )
        except TelegramError as error:
            logging.error("Не удалось уведомить пользователя об отказе команды: %s", error)

    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="🏠 Главное меню администратора:",
        reply_markup=get_main_keyboard(ADMIN_ID, admin_mode=True),
    )
    return ConversationHandler.END
