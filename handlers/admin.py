"""Административные разделы: пользователи, заявки и удаление сотрудников."""
from bot_context import *
from storage import load_json, save_json, load_pending, save_pending
from keyboards import cancel_keyboard, get_extra_keyboard, get_main_keyboard, get_registration_group_keyboard
from services import _normalize_person_name, notify_user_bot_stopped
from organization import is_admin_mode
from roles import get_user_group
from handlers.requests import process_registration_approval, requests_callback, show_requests_menu, _show_requests_after_callback


def _pending_request_name(raw_request) -> str:
    if isinstance(raw_request, dict):
        return str(raw_request.get("name") or "Пользователь")
    return str(raw_request)


async def enter_admin_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ Команда доступна только администратору.")
        return ConversationHandler.END
    context.user_data["admin_mode"] = True
    await update.message.reply_text(
        "🛡 **Режим администратора включён.**\nДля возврата в режим coor R используйте /coor.",
        reply_markup=get_main_keyboard(ADMIN_ID, admin_mode=True),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def exit_admin_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ Команда доступна только администратору.")
        return ConversationHandler.END
    context.user_data["admin_mode"] = False
    group = await get_user_group(ADMIN_ID) or "coor R"
    await update.message.reply_text(
        "👥 **Режим coor R включён.**\nДля возврата к административным функциям используйте /admin.",
        reply_markup=get_main_keyboard(ADMIN_ID, group=group, admin_mode=False),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def open_extra_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_mode(update.effective_user.id, context):
        await update.message.reply_text("⛔️ У вас нет доступа к этому разделу.")
        return ConversationHandler.END

    await update.message.reply_text(
        "⚙️ **Раздел «Дополнительно»**\n\nВыберите необходимое действие:",
        reply_markup=get_extra_keyboard(),
        parse_mode="Markdown",
    )
    return EXTRA_MENU_STATE


async def show_registered_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_mode(update.effective_user.id, context):
        await update.message.reply_text("⛔️ У вас нет доступа к этой команде.")
        return ConversationHandler.END

    users_data = await load_json(USERS_FILE)
    groups_data = await load_json(GROUPS_FILE)
    kpi_data = await load_json(KPI_FILE)
    issuance_data = await load_json(ISSUANCE_FILE)

    registered = []
    registered_names = set()
    service_ids_by_name = {}
    data_people = {}

    def add_data_person(name, source):
        display_name = str(name or "").strip()
        normalized_name = _normalize_person_name(display_name)
        if not normalized_name or normalized_name == "nan":
            return
        person = data_people.setdefault(
            normalized_name,
            {"name": display_name, "sources": set(), "service_id": None},
        )
        person["sources"].add(source)

    for uid, name in users_data.items():
        uid = str(uid)
        display_name = str(name or "").strip()
        if uid.isdigit():
            group_record = groups_data.get(uid, {})
            group = group_record.get("group", "—") if isinstance(group_record, dict) else "—"
            registered.append({"uid": uid, "name": display_name, "group": group})
            registered_names.add(_normalize_person_name(display_name))
        else:
            normalized_name = _normalize_person_name(display_name)
            service_ids_by_name.setdefault(normalized_name, uid)
            add_data_person(display_name, "данные")

    for record in kpi_data.values():
        if isinstance(record, dict):
            add_data_person(record.get("original_name"), "KPI")

    for uid, record in issuance_data.items():
        if str(uid).startswith("_") or not isinstance(record, dict):
            continue
        add_data_person(record.get("name"), "выдачи")

    unregistered = []
    for normalized_name, person in data_people.items():
        if normalized_name in registered_names:
            continue
        person["service_id"] = service_ids_by_name.get(normalized_name)
        unregistered.append(person)

    registered.sort(key=lambda item: item["name"].casefold())
    unregistered.sort(key=lambda item: item["name"].casefold())

    response_parts = [
        f"👥 **Зарегистрированные пользователи ({len(registered)}):**\n"
    ]
    user_index_map = {}
    current_index = 1

    if registered:
        for person in registered:
            user_index_map[current_index] = {
                "uid": person["uid"],
                "name": person["name"],
                "registered": True,
            }
            response_parts.append(
                f"{current_index}. *{person['name']}* — ID: `{person['uid']}` — Группа: **{person['group']}**"
            )
            current_index += 1
    else:
        response_parts.append("_Зарегистрированных пользователей нет._")

    response_parts.append(f"\n🕒 **Ещё не зарегистрированы ({len(unregistered)}):**\n")
    if unregistered:
        for person in unregistered:
            service_id = person.get("service_id")
            user_index_map[current_index] = {
                "uid": service_id,
                "name": person["name"],
                "registered": False,
            }
            sources = ", ".join(sorted(person["sources"]))
            response_parts.append(
                f"{current_index}. *{person['name']}* — источник: {sources}"
            )
            current_index += 1
    else:
        response_parts.append("_Все сотрудники из KPI и выдач зарегистрированы._")

    context.user_data["user_index_map"] = user_index_map
    await update.message.reply_text(
        "\n".join(response_parts),
        reply_markup=get_extra_keyboard(),
        parse_mode="Markdown",
    )
    return EXTRA_MENU_STATE


async def show_pending_requests_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Legacy alias: экран заявок всегда строится единым inbox-обработчиком."""
    return await show_requests_menu(update, context)


async def pending_requests_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Совместимость со старыми кнопками через единый inbox-обработчик."""
    query = update.callback_query
    data = query.data
    if data == "pend_back":
        await query.answer()
        await query.message.delete()
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="⚙️ Раздел «Дополнительно»:",
            reply_markup=get_extra_keyboard(),
        )
        return EXTRA_MENU_STATE

    await query.answer()
    pending = await load_pending()
    if data == "pend_accept_all":
        approved_count = 0
        for uid_str in list(pending):
            result = await process_registration_approval(uid_str, accepted=True)
            if result is None:
                continue
            approved_count += 1
            try:
                await context.bot.send_message(
                    chat_id=int(uid_str),
                    text=result["user_text"],
                    reply_markup=get_main_keyboard(int(uid_str), result["group"]),
                )
            except Exception as error:
                logging.warning("Не удалось уведомить пользователя %s: %s", uid_str, error)
        return await _show_requests_after_callback(
            query,
            context,
            f"✅ Одобрено заявок: {approved_count}.",
        )

    if data.startswith("pend_accept:"):
        _, uid_str = data.split(":", 1)
        result = await process_registration_approval(uid_str, accepted=True)
        if result is None:
            await query.answer("Эта заявка уже обработана или удалена.", show_alert=True)
            return await _show_requests_after_callback(query, context)
        try:
            await context.bot.send_message(
                chat_id=int(uid_str),
                text=result["user_text"],
                reply_markup=get_main_keyboard(int(uid_str), result["group"]),
            )
        except Exception as error:
            logging.warning("Не удалось уведомить пользователя %s: %s", uid_str, error)
        return await _show_requests_after_callback(
            query,
            context,
            f"✅ Заявка пользователя *{result['name']}* одобрена.",
        )

    return PENDING_REQUESTS_STATE


async def request_user_number_to_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_mode(update.effective_user.id, context):
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
    target_uid = target_user.get("uid")
    target_name = target_user["name"]

    if not target_uid:
        await update.message.reply_text(
            "ℹ️ Эта запись есть в KPI/выдачах, но Telegram-пользователь ещё не зарегистрирован. "
            "Удаление по номеру доступно только для записей users.json.",
            reply_markup=get_extra_keyboard(),
        )
        return EXTRA_MENU_STATE

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


async def admin_moderation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает старые adm_* кнопки через тот же canonical req_* поток."""
    query = update.callback_query
    action, target_id_str = query.data.split(":", 1)
    if action not in {"adm_accept", "adm_reject"}:
        return
    original_data = query.data
    query.data = f"{'req_accept' if action == 'adm_accept' else 'req_reject'}:registration:{target_id_str}"
    try:
        return await requests_callback(update, context)
    finally:
        query.data = original_data
