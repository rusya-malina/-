"""Административные разделы: пользователи, заявки и удаление сотрудников."""
from bot_context import *
from storage import load_json, save_json, load_pending, save_pending
from keyboards import cancel_keyboard, get_extra_keyboard, get_main_keyboard, get_registration_group_keyboard
from services import notify_user_bot_stopped


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


async def admin_moderation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
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
