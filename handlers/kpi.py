"""Загрузка, ручное редактирование и просмотр KPI."""
import contextlib
import math

from application.admin_service import EmployeeAdminService
from application.kpi_service import KpiService, build_plan_projection
from application.report_service import ReportService
from application.team_kpi_service import CALCULATION_VERSION, TeamKpiService
from application.training_service import TrainingService
from bot_context import (
    BadRequest,
    ContextTypes,
    ConversationHandler,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from config import (
    GROUPS_FILE,
    GROUPS_WITH_BALANCES,
    GROUPS_WITH_HOURS,
    GROUPS_WITH_PLAN,
    GROUPS_WITH_TRAINING,
    ISSUANCE_FILE,
    KPI_FILE,
    TEAM_OPTIONS,
    TRAINING_HISTORY_FILE,
    USERS_FILE,
)
from data_models import user_name
from keyboards import cancel_keyboard, get_data_keyboard, get_main_keyboard
from organization import (
    build_employee_registry,
    get_employee_by_id,
    get_visible_users,
    is_management_group,
    merge_employee_issuance,
)
from permissions import Permission, has_permission, is_admin_mode
from roles import get_user_group
from services import (
    _format_quantity,
    calculate_balances,
    notify_user_bot_stopped,
    notify_user_kpi_updated,
)
from states import (
    CONFIRM_DELETE_EMP,
    KPI_MENU_STATE,
    MANUAL_KPI_FIELD_HOURS,
    MANUAL_KPI_GT_FACT,
    MANUAL_KPI_MICRO_LAS_FACT,
    MANUAL_KPI_MICRO_LAU_FACT,
    MANUAL_KPI_NAME,
    MANUAL_KPI_NEW_NAME,
    MANUAL_KPI_OFFICE_HOURS,
    MANUAL_KPI_RETRAFIC_FACT,
    SELECT_PREVIOUS_EMP,
    SET_PLAN_GT,
    SET_PLAN_MICRO,
    SET_PLAN_RETRAFIC,
)
from storage import get_default_plans, load_json


async def open_kpi_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, context, Permission.KPI_MANAGEMENT):
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
    result = await KpiService.from_default_storage().set_default_plans(plans)
    if not result.ok:
        await update.message.reply_text("❌ Не удалось сохранить общие планы.")
        return SET_PLAN_RETRAFIC

    await update.message.reply_text(
        "✅ **Общие планы успешно обновлены!**",
        reply_markup=get_main_keyboard(user_id_num, admin_mode=True),
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
    if not is_admin_mode(update.effective_user.id, context):
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
            reply_markup=get_main_keyboard(user_id_num, admin_mode=True),
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
            reply_markup=get_main_keyboard(user_id_num, admin_mode=True),
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
            reply_markup=get_main_keyboard(user_id_num, admin_mode=True),
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
        status_text = f"🗑 **Сотрудник {target_name} удалён из списка KPI.**"
        if del_type == "full":
            users = await load_json(USERS_FILE)
            groups = await load_json(GROUPS_FILE)
            kpi_data = await load_json(KPI_FILE)
            issuance_data = await load_json(ISSUANCE_FILE)
            employees = build_employee_registry(users, groups, kpi_data, issuance_data)
            target = next(
                (employee for employee in employees if employee["name"].casefold() == target_name.casefold()),
                None,
            )
            if target is None or not target.get("user_id"):
                operation = await KpiService.from_default_storage().delete_entry(target_name)
            else:
                operation = await EmployeeAdminService.from_default_storage().delete_registered(
                    target["user_id"],
                    user_id_num,
                )
            if operation.ok and target is not None and str(target.get("user_id", "")).isdigit():
                await notify_user_bot_stopped(context, target["user_id"])
            status_text = f"🔥 **Сотрудник {target_name} полностью удалён!**" if operation.ok else (
                f"⚠️ **Не удалось удалить сотрудника {target_name}.**"
            )
        else:
            operation = await KpiService.from_default_storage().delete_entry(target_name)
            if not operation.ok:
                status_text = f"⚠️ **Запись KPI сотрудника {target_name} не найдена.**"

        await query.message.delete()
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=status_text,
            reply_markup=get_main_keyboard(user_id_num, admin_mode=True),
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

    result = await KpiService.from_default_storage().save_manual_entry(
        target_name,
        {
            "gt_fact": gt_fact,
            "micro_las_fact": las_fact,
            "micro_lau_fact": lau_fact,
            "retrafic_fact": retrafic_fact,
            "office_hours": office_hours,
            "field_hours": field_hours,
        },
    )
    if not result.ok:
        await update.message.reply_text("❌ Не удалось сохранить KPI. Проверьте введённые значения.")
        return MANUAL_KPI_FIELD_HOURS

    await TeamKpiService.from_default_storage().rebuild()
    await notify_user_kpi_updated(context, target_name)

    await update.message.reply_text(
        f"✅ **KPI успешно сохранены для {target_name}!**",
        reply_markup=get_main_keyboard(user_id_num, admin_mode=True),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


def my_kpi_markup(group: str | None, admin_mode: bool) -> InlineKeyboardMarkup:
    manager_mode = admin_mode or is_management_group(group)
    kpi_callback = "my_kpi_show_team" if manager_mode else "my_kpi_show_kpi"
    inline_keyboard = [[InlineKeyboardButton("📊 KPI", callback_data=kpi_callback)]]
    if admin_mode or group in GROUPS_WITH_HOURS:
        inline_keyboard.append([InlineKeyboardButton("⏱️ Часы", callback_data="my_kpi_show_hours")])
    if group in GROUPS_WITH_TRAINING:
        inline_keyboard.append([InlineKeyboardButton("📚 Обучения", callback_data="my_kpi_show_trainings")])
    return InlineKeyboardMarkup(inline_keyboard)


def build_monthly_training_report(
    visible_users: list[dict],
    training_history: dict,
    month: str | None = None,
) -> str:
    selected_month = month or TrainingService.current_month()
    lines = [f"📚 Обучения за текущий месяц ({selected_month})", "━━━━━━━━━━━━━━━━━━"]
    employees = sorted(visible_users, key=lambda item: str(item.get("name", "")).casefold())
    if not employees:
        lines.append("Нет зарегистрированных подчинённых сотрудников.")
    else:
        for employee in employees:
            aliases = employee.get("aliases", [])
            count = TrainingService.delivery_count_from_data(training_history, aliases, selected_month)
            lines.append(f"👤 {employee.get('name', 'Сотрудник')} — {count}")
    return "\n".join(lines)


def _team_metric_line(label: str, metric: dict) -> str:
    return (
        f"{label}: План: `{float(metric.get('plan', 0)):.0f}` | "
        f"Факт: `{float(metric.get('fact', 0)):.0f}` (`{float(metric.get('percent', 0)):.1f}%`)"
    )


def _team_report_lines(report: dict, title: str) -> list[str]:
    metrics = report.get("metrics", {})
    microacts = metrics.get("microacts", {})
    las_fact = float(microacts.get("las_fact", 0))
    lau_fact = float(microacts.get("lau_fact", 0))
    las_percent = float(microacts.get("las_percent", 0))
    lines = [
        f"🏷 **{title}**",
        f"👥 Сотрудников: **{report.get('employee_count', 0)}**",
        f"📈 {_team_metric_line('GT', metrics.get('gt', {}))}",
        f"🎯 {_team_metric_line('Микроакты', microacts)}",
        f"  ├ Факт по LAS: `{las_fact:.0f}` | Факт по LAU: `{lau_fact:.0f}`",
        f"  └ Итоговый LAS %: `{las_percent:.2f}%`",
        f"🔄 {_team_metric_line('Re-trafic', metrics.get('retrafic', {}))}",
    ]
    return lines


def _team_work_time_lines(report: dict) -> list[str]:
    work_time = report.get("metrics", {}).get("work_time", {})
    employee_count = int(work_time.get("employee_count", report.get("employee_count", 0)) or 0)
    plan = float(work_time.get("plan", employee_count * 64) or 0)
    fact = float(work_time.get("fact", 0) or 0)
    office_hours = float(work_time.get("office_hours", 0) or 0)
    field_hours = float(work_time.get("field_hours", 0) or 0)
    percent = float(work_time.get("percent", 0) or 0)
    return [
        "",
        "⏱️ **Время работы подчинённой команды**",
        f"👥 Сотрудников: **{employee_count}**",
        f"📌 План: `{plan:.1f}` ч. (64 ч. на человека)",
        f"✅ Факт для выполнения (поле): `{fact:.1f}` ч.",
        f"🏢 Факт офис: `{office_hours:.1f}` ч. (не входит в выполнение)",
        f"⛺️ Факт поле: `{field_hours:.1f}` ч.",
        f"📊 Выполнение: `{percent:.1f}%`",
    ]


def build_team_kpi_report(snapshot: dict, manager_group: str) -> str:
    report = snapshot.get("manager_reports", {}).get(manager_group)
    if not isinstance(report, dict):
        return "ℹ️ Командный KPI пока не рассчитан."

    lines = [
        "📊 **Показатели KPI**",
        f"👤 Руководитель: *{manager_group}*",
        f"📆 Период: `{snapshot.get('period', '—')}`",
        "━━━━━━━━━━━━━━━━━━",
    ]
    lines.extend(_team_report_lines(report, "Командный KPI"))
    if manager_group in {"coor A", "coor R"}:
        lines.extend(_team_work_time_lines(report))

    if manager_group in {"SPV", "MNG"}:
        lines.extend(["", "━━━━━━━━━━━━━━━━━━", "📌 **Показатели по командам**"])
        for team_group in ("A LAMP", "R LAMP"):
            team_report = snapshot.get("teams", {}).get(team_group)
            if isinstance(team_report, dict):
                lines.extend(["", *_team_report_lines(team_report, team_group)])

    missing_count = len(report.get("quality", {}).get("missing_employee_ids", []))
    if missing_count:
        lines.append(f"⚠️ Нет KPI-данных у сотрудников: **{missing_count}**")
    return "\n".join(lines)


async def my_kpi_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Switching to KPI must close any stale training flow in the same chat.
    for key in ("training_recipient_id", "training_recipient_name", "training_type"):
        context.user_data.pop(key, None)
    context.user_data["active_flow"] = "my_kpi"
    user_id_num = update.effective_user.id
    user_id = str(user_id_num)
    users = await load_json(USERS_FILE)
    group = await get_user_group(user_id_num)

    admin_mode = is_admin_mode(user_id_num, context)
    if user_id not in users and not admin_mode:
        await update.message.reply_text("⚠️ Вы еще не зарегистрированы. Нажмите /start.")
        return ConversationHandler.END
    if not admin_mode and group not in TEAM_OPTIONS:
        await update.message.reply_text("⚠️ Ваша группа ещё не подтверждена. Нажмите /start.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📌 **Раздел «Мой KPI»**\n\nВыберите интересующий раздел:",
        reply_markup=my_kpi_markup(group, admin_mode),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def my_kpi_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id_num = query.from_user.id
    user_id = str(user_id_num)
    users = await load_json(USERS_FILE)
    groups = await load_json(GROUPS_FILE)
    kpi_data = await load_json(KPI_FILE)
    issuance_data = await load_json(ISSUANCE_FILE)
    group = await get_user_group(user_id_num)

    admin_mode = is_admin_mode(user_id_num, context)
    if data == "my_kpi_show_hours" and not admin_mode and group not in GROUPS_WITH_HOURS:
        await query.answer("Раздел «Часы» недоступен для вашей группы.", show_alert=True)
        return
    if data == "my_kpi_show_team" and not admin_mode and not is_management_group(group):
        await query.answer("Командный KPI доступен только руководителям.", show_alert=True)
        return
    if data == "my_kpi_show_trainings" and group not in GROUPS_WITH_TRAINING:
        await query.answer("Раздел «Обучения» доступен только coor A и coor R.", show_alert=True)
        return

    await query.answer()

    if data == "my_kpi_show_team":
        manager_group = "MNG" if admin_mode else group
        service = TeamKpiService.from_default_storage()
        snapshot = await service.load_current()
        manager_report = snapshot.get("manager_reports", {}).get(manager_group, {}) if snapshot else {}
        snapshot_version = snapshot.get("calculation_version") if snapshot else None
        has_work_time = isinstance(manager_report, dict) and "work_time" in manager_report.get("metrics", {})
        if snapshot is None or snapshot_version != CALCULATION_VERSION or not has_work_time:
            snapshot = await service.rebuild()
        await query.message.edit_text(
            build_team_kpi_report(snapshot, manager_group),
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Назад к меню KPI", callback_data="my_kpi_back")]]
            ),
            parse_mode="Markdown",
        )
        return

    if data == "my_kpi_back":
        await query.message.edit_text(
            "📌 **Раздел «Мой KPI»**\n\nВыберите интересующий раздел:",
            reply_markup=my_kpi_markup(group, admin_mode),
            parse_mode="Markdown",
        )
        return

    if data == "my_kpi_show_trainings":
        visible_users = get_visible_users(
            user_id_num,
            users,
            groups,
            exclude_user_id=user_id_num,
            kpi_data=kpi_data,
            issuance_data=issuance_data,
        )
        training_history = await load_json(TRAINING_HISTORY_FILE)
        report = build_monthly_training_report(visible_users, training_history)
        await query.message.edit_text(
            report,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Назад к меню KPI", callback_data="my_kpi_back")]]
            ),
        )
        return

    employee = get_employee_by_id(user_id, users, groups, kpi_data, issuance_data)
    user_name_value = employee["name"] if employee else user_name(users.get(user_id), "Администратор" if admin_mode else "")
    lookup_name = employee.get("name_key") if employee else user_name_value.strip().lower()

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
            micro_details += "  └ ✅ **Показатель LAS в норме!**\n"

        text = (
            f"📊 **Ваши показатели KPI**\n"
            f"👤 Сотрудник: *{user_name_value}*\n"
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
            f"👤 Сотрудник: *{user_name_value}*\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🏢 **Офисные часы:** `{office_hours:.1f}`\n"
            f"⛺️ **Полевые часы:** `{field_hours:.1f}` из 64 часов\n"
        )
        inline_keyboard = [[InlineKeyboardButton("⬅️ Назад к меню", callback_data="my_kpi_back")]]
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard), parse_mode="Markdown")



def _plan_rate(row: dict, metric: str) -> str:
    if row[f"{metric}_remaining"] <= 0:
        return "План перевыполнен"
    return f"{row[f'{metric}_per_hour_rounded']}/час"


def _plan_metric_status(target_100: dict, target_111: dict, metric: str) -> str:
    """Return a concise status for one KPI metric in the plan card."""
    remaining_100 = target_100[f"{metric}_remaining"]
    remaining_111 = target_111[f"{metric}_remaining"]
    if remaining_111 <= 0:
        return "План перевыполнен"
    if remaining_100 <= 0:
        return "Цель 100% выполнена"
    return "В работе"


def _plan_overall_status(target_100: dict, target_111: dict) -> str:
    """Return the overall status without hiding an unfinished KPI metric."""
    metrics = ("gt", "las", "lau")
    if all(target_111[f"{metric}_remaining"] <= 0 for metric in metrics):
        return "План перевыполнен"
    if all(target_100[f"{metric}_remaining"] <= 0 for metric in metrics):
        return "Цель 100% выполнена"
    return "В работе"


async def show_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users = await load_json(USERS_FILE)
    groups = await load_json(GROUPS_FILE)
    kpi_data = await load_json(KPI_FILE)
    issuance_data = await load_json(ISSUANCE_FILE)
    group = await get_user_group(update.effective_user.id)
    admin_mode = is_admin_mode(update.effective_user.id, context)
    if user_id not in users and not admin_mode:
        await update.message.reply_text("⚠️ Вы еще не зарегистрированы. Нажмите /start.")
        return
    if not admin_mode and group not in GROUPS_WITH_PLAN:
        await update.message.reply_text("⚠️ Раздел «План» доступен только сотрудникам A LAMP и R LAMP.")
        return

    employee = get_employee_by_id(user_id, users, groups, kpi_data, issuance_data)
    if not employee:
        await update.message.reply_text("ℹ️ Данные сотрудника для расчёта плана не найдены.")
        return
    entry = kpi_data.get(employee.get("name_key", ""), {})
    projection = build_plan_projection(entry)
    workdays_left = projection["workdays_left"]
    rows_by_target = {row["target_percent"]: row for row in projection["rows"]}
    target_100 = rows_by_target[100]
    target_111 = rows_by_target[111]
    gt_status = _plan_metric_status(target_100, target_111, "gt")
    las_status = _plan_metric_status(target_100, target_111, "las")
    lau_status = _plan_metric_status(target_100, target_111, "lau")
    overall_status = _plan_overall_status(target_100, target_111)
    current_threshold_percent = projection["current_threshold_percent"]
    threshold_status = "соблюдён" if current_threshold_percent > 40 else "ниже нормы"

    def microacts_plan_line(row: dict) -> str:
        las_total = row["las_remaining"]
        lau_total = row["lau_remaining"]
        return (
            f"{row['target_percent']}% план — "
            f"LAS: `{_plan_rate(row, 'las')}` | "
            f"LAU: `{_plan_rate(row, 'lau')}` "
            f"(Итого LAS: `{math.ceil(las_total)}`, "
            f"LAU: `{math.ceil(lau_total)}`)"
        )

    text = "\n".join(
        [
            "📊 **Персональная карточка плана**",
            f"👤 *{employee['name']}*",
            f"📆 На дату: `{projection['as_of']}`",
            f"🗓 Осталось рабочих дней — {workdays_left}",
            "",
            "📈 **GT**",
            f"100% — `{_plan_rate(target_100, 'gt')}`",
            f"111% — `{_plan_rate(target_111, 'gt')}`",
            f"Статус — **{gt_status}**",
            "",
            "🎯 **Микроакты LAS / LAU**",
            f"Текущий threshold LAS: `{current_threshold_percent:.2f}%` — **{threshold_status}** (норма > 40%)",
            microacts_plan_line(target_100),
            microacts_plan_line(target_111),
            f"Статус LAS — **{las_status}**",
            f"Статус LAU — **{lau_status}**",
            "",
            f"📌 **Общий статус — {overall_status}**",
        ]
    )
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_main_keyboard(update.effective_user.id, group=group, admin_mode=admin_mode),
    )


async def show_balances(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    users = await load_json(USERS_FILE)
    groups = await load_json(GROUPS_FILE)
    kpi_data = await load_json(KPI_FILE)
    issuance_data = await load_json(ISSUANCE_FILE)
    group = await get_user_group(user_id)
    admin_mode = is_admin_mode(update.effective_user.id, context)
    if user_id not in users and not admin_mode:
        await update.message.reply_text("⚠️ Вы еще не зарегистрированы. Нажмите /start.")
        return
    if not admin_mode and group not in GROUPS_WITH_BALANCES:
        await update.message.reply_text("⚠️ Остатки недоступны для вашей группы.")
        return

    employee = get_employee_by_id(user_id, users, groups, kpi_data, issuance_data)
    user_name_value = employee["name"] if employee else user_name(users.get(user_id), "Администратор")
    if employee:
        report = await ReportService.from_default_storage().personal_report(employee)
        balances = report["balances"]
    else:
        lookup_name = user_name_value.strip().lower()
        user_kpi = kpi_data.get(lookup_name, {})
        issued = merge_employee_issuance(employee, issuance_data)
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
        f"👤 Сотрудник: *{user_name_value}*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{balance_line('MINTS', mints_issued, microacts_done, mints_balance)}\n\n"
        f"{balance_line('Стики', sticks_issued, gt_done, sticks_balance)}\n\n"
        f"ℹ️ Микроакты = LAS (`{_format_quantity(balances['las_done'])}`) + "
        f"LAU (`{_format_quantity(balances['lau_done'])}`)."
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard(update.effective_user.id, group=group, admin_mode=admin_mode))


async def kpi_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users = await load_json(USERS_FILE)
    group = await get_user_group(user_id)
    if not is_admin_mode(user_id, context) and (str(user_id) not in users or group not in TEAM_OPTIONS):
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
        await context.bot.send_message(chat_id=query.message.chat_id, text="🏠 Главное меню:", reply_markup=get_main_keyboard(user_id_num, group=await get_user_group(user_id_num), admin_mode=is_admin_mode(user_id_num, context)))
        return

    with contextlib.suppress(BadRequest):
        await query.message.edit_text(text, reply_markup=query.message.reply_markup, parse_mode="Markdown")
