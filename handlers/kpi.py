"""Загрузка, ручное редактирование и просмотр KPI."""


from bot_context import *


from storage import load_json, save_json, get_default_plans


from keyboards import cancel_keyboard, get_data_keyboard, get_main_keyboard


from services import (
    _format_quantity,
    calculate_balances,
    notify_user_bot_stopped,
    notify_user_kpi_updated,
)
from roles import get_user_group


async def open_kpi_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔️ У вас нет доступа к этому разделу.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📥 **Загрузка данных**\n\nВыберите действие: загрузка KPI, выдача MINTS/стиков или выгрузка статистики.",
        reply_markup=get_data_keyboard(),
        parse_mode="Markdown",
    )
    return KPI_MENU_STATE


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


async def my_kpi_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id_num = update.effective_user.id
    user_id = str(user_id_num)
    users = await load_json(USERS_FILE)
    group = await get_user_group(user_id_num)

    if user_id not in users and user_id_num != ADMIN_ID:
        await update.message.reply_text("⚠️ Вы еще не зарегистрированы. Нажмите /start.")
        return
    if user_id_num != ADMIN_ID and group not in TEAM_OPTIONS:
        await update.message.reply_text("⚠️ Ваша группа ещё не подтверждена. Нажмите /start.")
        return

    inline_keyboard = [[InlineKeyboardButton("📊 KPI", callback_data="my_kpi_show_kpi")]]
    if user_id_num == ADMIN_ID or group in GROUPS_WITH_HOURS:
        inline_keyboard.append([InlineKeyboardButton("⏱️ Часы", callback_data="my_kpi_show_hours")])
    await update.message.reply_text(
        "📌 **Раздел «Мой KPI»**\n\nВыберите интересующий раздел:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard),
        parse_mode="Markdown",
    )


async def my_kpi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id_num = query.from_user.id
    user_id = str(user_id_num)
    users = await load_json(USERS_FILE)
    group = await get_user_group(user_id_num)

    if data == "my_kpi_show_hours" and user_id_num != ADMIN_ID and group not in GROUPS_WITH_HOURS:
        await query.answer("Раздел «Часы» недоступен для вашей группы.", show_alert=True)
        return

    await query.answer()

    if data == "my_kpi_back":
        inline_keyboard = [[InlineKeyboardButton("📊 KPI", callback_data="my_kpi_show_kpi")]]
        if user_id_num == ADMIN_ID or group in GROUPS_WITH_HOURS:
            inline_keyboard.append([InlineKeyboardButton("⏱️ Часы", callback_data="my_kpi_show_hours")])
        await query.message.edit_text(
            "📌 **Раздел «Мой KPI»**\n\nВыберите интересующий раздел:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard),
            parse_mode="Markdown",
        )
        return

    user_name = users.get(user_id, "Администратор" if user_id_num == ADMIN_ID else "")
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
            f"  ├ Факт по LAS: `{las_fact:.0f}` | Факт по LAU: `{lau_fact:.0f}`\n"
            f"  ├ Итоговый LAS %: `{las_percent:.2f}%`\n"
        )
        if need_las > 0:
            micro_details += f"  └ ⚠️ **Рекомендация:** Добавить микроакты LAS: `{need_las}`\n"
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



async def show_balances(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users = await load_json(USERS_FILE)
    group = await get_user_group(user_id)
    if user_id not in users and user_id != str(ADMIN_ID):
        await update.message.reply_text("⚠️ Вы еще не зарегистрированы. Нажмите /start.")
        return
    if user_id != str(ADMIN_ID) and group not in GROUPS_WITH_BALANCES:
        await update.message.reply_text("⚠️ Остатки недоступны для вашей группы.")
        return

    user_name = users.get(user_id, "Администратор")
    lookup_name = user_name.strip().lower()
    kpi_data = await load_json(KPI_FILE)
    user_kpi = kpi_data.get(lookup_name, {})
    issuance_data = await load_json(ISSUANCE_FILE)
    issued = issuance_data.get(user_id, {})

    balances = calculate_balances(user_kpi, issued)
    mints_issued = balances["mints_issued"]
    sticks_issued = balances["sticks_issued"]
    microacts_done = balances["mints_used"]
    gt_done = balances["sticks_used"]
    mints_balance = balances["mints_balance"]
    sticks_balance = balances["sticks_balance"]

    def balance_line(label: str, issued_value: float, spent_value: float, balance: float) -> str:
        warning = " ⚠️" if balance < 0 else ""
        return (
            f"{label}: **{_format_quantity(balance)}**{warning}\n"
            f"  Выдано: `{_format_quantity(issued_value)}` − использовано: `{_format_quantity(spent_value)}`"
        )

    text = (
        f"📦 **Остатки**\n"
        f"👤 Сотрудник: *{user_name}*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{balance_line('MINTS', mints_issued, microacts_done, mints_balance)}\n\n"
        f"{balance_line('Стики', sticks_issued, gt_done, sticks_balance)}\n\n"
        f"ℹ️ Микроакты = LAS (`{_format_quantity(balances['las_done'])}`) + "
        f"LAU (`{_format_quantity(balances['lau_done'])}`)."
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard(update.effective_user.id))


async def kpi_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users = await load_json(USERS_FILE)
    group = await get_user_group(user_id)
    if user_id != ADMIN_ID and (str(user_id) not in users or group not in TEAM_OPTIONS):
        await update.message.reply_text("⚠️ Сначала завершите регистрацию через /start.")
        return

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
