"""Административные разделы: пользователи, заявки и удаление сотрудников."""
from bot_context import *
from storage import load_json, save_json, load_pending, save_pending
from keyboards import cancel_keyboard, get_extra_keyboard, get_main_keyboard, get_registration_group_keyboard
from services import _normalize_person_name, notify_user_bot_stopped
from organization import is_admin_mode
from roles import get_user_group


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
    if not is_admin_mode(update.effective_user.id, context):
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
    query = update.callback_query
    await query.answer()
    if not is_admin_mode(query.from_user.id, context):
        await query.answer("⛔️ Нет доступа.", show_alert=True)
        return

    action, target_id_str = query.data.split(":", 1)
    target_id = int(target_id_str)
    pending = await load_pending()
    request = pending.get(target_id_str)
    if not request:
        await query.answer("Заявка уже обработана или устарела.", show_alert=True)
        return

    if isinstance(request, dict):
        full_name = str(request.get("name", "Пользователь"))
        group = str(request.get("group", ""))
    else:
        full_name = str(request)
        group = ""

    if action == "adm_accept":
        users = await load_json(USERS_FILE)
        users[target_id_str] = full_name
        await save_json(users, USERS_FILE)

        groups = await load_json(GROUPS_FILE)
        groups[target_id_str] = {
            "name": full_name,
            "group": group,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await save_json(groups, GROUPS_FILE)
        pending.pop(target_id_str, None)
        await save_pending(pending)

        await query.message.edit_text(
            f"✅ **Заявка одобрена.**\nПользователь *{full_name}* зарегистрирован.\nГруппа: **{group}**",
            parse_mode="Markdown",
        )
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"🎉 **Ваша заявка одобрена!**\n\nДобро пожаловать, {full_name}!\nГруппа: **{group}**",
                reply_markup=get_main_keyboard(target_id, group),
                parse_mode="Markdown",
            )
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление пользователю {target_id}: {e}")
    elif action == "adm_reject":
        pending.pop(target_id_str, None)
        await save_pending(pending)
        groups = await load_json(GROUPS_FILE)
        groups.pop(target_id_str, None)
        await save_json(groups, GROUPS_FILE)

        await query.message.edit_text(
            f"❌ **Заявка отклонена.**\nПользователь *{full_name}* должен выбрать группу заново.",
            parse_mode="Markdown",
        )
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="❌ Заявка отклонена. Выберите группу заново, чтобы отправить новую заявку:",
                reply_markup=get_registration_group_keyboard(),
            )
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление об отказе пользователю {target_id}: {e}")
