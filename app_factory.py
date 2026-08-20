"""Сборка Telegram Application и маршрутизация по функциональным модулям."""
from bot_context import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    HTTPXRequest,
    MessageHandler,
    filters,
)
from handlers.admin import (
    enter_admin_mode,
    exit_admin_mode,
    open_extra_menu,
    pending_requests_callback,
    process_delete_user_by_number,
    request_user_number_to_delete,
    show_registered_users,
)
from handlers.broadcast import (
    send_broadcast,
    start_broadcast,
)
from handlers.issuance import (
    issuance_callback,
    issuance_menu_message,
    process_issuance_amount,
)
from handlers.kpi import (
    delete_employee_confirm,
    kpi_callback,
    kpi_menu,
    manual_kpi_get_field_hours,
    manual_kpi_get_gt_fact,
    manual_kpi_get_micro_las_fact,
    manual_kpi_get_micro_lau_fact,
    manual_kpi_get_new_name,
    manual_kpi_get_office_hours,
    manual_kpi_get_retrafic_fact,
    manual_kpi_select_employee,
    my_kpi_callback,
    my_kpi_menu,
    open_kpi_admin_menu,
    select_previous_employee_handler,
    set_plan_gt,
    set_plan_micro,
    set_plan_retrafic,
    show_balances,
)
from handlers.requests import (
    requests_callback,
    show_requests_menu,
)
from handlers.teams import (
    open_my_team_menu,
    process_team_selection,
    show_team_balances,
    show_team_kpi,
    start_team_selection,
    team_moderation_callback,
)
from handlers.uploads import (
    process_excel_file,
    process_issuance_excel_file,
    start_excel_upload,
)
from handlers.user import (
    cancel_action,
    get_las,
    get_lau,
    new_calculation,
    reg_get_first_name,
    reg_get_group,
    reg_get_last_name,
    save_new_first_name,
    save_new_full_name,
    start,
)
from services import check_pending_requests_job
from states import (
    BROADCAST,
    CHANGE_LAST_NAME,
    CHANGE_NAME,
    CONFIRM_DELETE_EMP,
    DELETE_BY_NUM_STATE,
    EXTRA_MENU_STATE,
    ISSUANCE_AMOUNT,
    ISSUANCE_EXCEL_UPLOAD,
    ISSUANCE_MENU,
    ISSUANCE_USER,
    KPI_MENU_STATE,
    LAS,
    LAU,
    MANUAL_KPI_FIELD_HOURS,
    MANUAL_KPI_GT_FACT,
    MANUAL_KPI_MICRO_LAS_FACT,
    MANUAL_KPI_MICRO_LAU_FACT,
    MANUAL_KPI_NAME,
    MANUAL_KPI_NEW_NAME,
    MANUAL_KPI_OFFICE_HOURS,
    MANUAL_KPI_RETRAFIC_FACT,
    PENDING_REQUESTS_STATE,
    REG_FIRST_NAME,
    REG_GROUP,
    REG_LAST_NAME,
    SELECT_PREVIOUS_EMP,
    SET_PLAN_GT,
    SET_PLAN_MICRO,
    SET_PLAN_RETRAFIC,
    TEAM_MENU_STATE,
    TEAM_SELECTION,
    UPLOAD_EXCEL,
)


def build_application(token: str) -> Application:
    """Создаёт приложение, подключает фоновые задачи и маршруты Telegram."""
    request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    app = Application.builder().token(token).request(request).build()

    if app.job_queue:
        app.job_queue.run_repeating(check_pending_requests_job, interval=300, first=60)

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("admin", enter_admin_mode),
            CommandHandler("coor", exit_admin_mode),
            MessageHandler(filters.Regex(r"^Новый расчет$"), new_calculation),
            MessageHandler(filters.Regex(r"^Моя команда$"), open_my_team_menu),
            MessageHandler(filters.Regex(r"^Определить команду$"), start_team_selection),
            MessageHandler(filters.Regex(r"^📢 Рассылка$"), start_broadcast),
            MessageHandler(filters.Regex(r"^Загрузить данные$"), open_kpi_admin_menu),
            MessageHandler(filters.Regex(r"^⚙️ Дополнительно$"), open_extra_menu),
        ],
        states={
            REG_GROUP: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, reg_get_group)],
            REG_FIRST_NAME: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, reg_get_first_name)],
            REG_LAST_NAME: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, reg_get_last_name)],
            LAS: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, get_las)],
            LAU: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, get_lau)],
            CHANGE_NAME: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_first_name)],
            CHANGE_LAST_NAME: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_full_name)],
            BROADCAST: [
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
                MessageHandler(filters.PHOTO, send_broadcast),
                MessageHandler(filters.Document.ALL, send_broadcast),
                MessageHandler(filters.TEXT & ~filters.COMMAND, send_broadcast),
            ],
            KPI_MENU_STATE: [
                MessageHandler(filters.Regex(r"^📥 Загрузить KPI \(Excel\)$"), start_excel_upload),
                MessageHandler(filters.Regex(r"^(MINTS|Стики|📥 Загрузить выдачи \(Excel\)|📊 Выгрузка статистики)$"), issuance_menu_message),
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
            ],
            UPLOAD_EXCEL: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.Document.ALL, process_excel_file)],
            MANUAL_KPI_NAME: [CallbackQueryHandler(manual_kpi_select_employee, pattern=r"^manual_emp_")],
            SELECT_PREVIOUS_EMP: [CallbackQueryHandler(select_previous_employee_handler, pattern=r"^(sel_emp:|manual_emp_)")],
            CONFIRM_DELETE_EMP: [CallbackQueryHandler(delete_employee_confirm, pattern=r"^(del_select:|del_type:|del_back_list|manual_emp_)")],
            MANUAL_KPI_NEW_NAME: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, manual_kpi_get_new_name)],
            MANUAL_KPI_GT_FACT: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, manual_kpi_get_gt_fact)],
            MANUAL_KPI_MICRO_LAS_FACT: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, manual_kpi_get_micro_las_fact)],
            MANUAL_KPI_MICRO_LAU_FACT: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, manual_kpi_get_micro_lau_fact)],
            MANUAL_KPI_RETRAFIC_FACT: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, manual_kpi_get_retrafic_fact)],
            MANUAL_KPI_OFFICE_HOURS: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, manual_kpi_get_office_hours)],
            MANUAL_KPI_FIELD_HOURS: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, manual_kpi_get_field_hours)],
            SET_PLAN_GT: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, set_plan_gt)],
            SET_PLAN_MICRO: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, set_plan_micro)],
            SET_PLAN_RETRAFIC: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, set_plan_retrafic)],
            EXTRA_MENU_STATE: [
                CallbackQueryHandler(requests_callback, pattern=r"^req_"),
                CallbackQueryHandler(team_moderation_callback, pattern=r"^team_(accept|reject):"),
                MessageHandler(filters.Regex(r"^👥 Пользователи$"), show_registered_users),
                MessageHandler(filters.Regex(r"^📥 Заявки$"), show_requests_menu),
                MessageHandler(filters.Regex(r"^🗑 Удалить по номеру$"), request_user_number_to_delete),
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
            ],
            DELETE_BY_NUM_STATE: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, process_delete_user_by_number)],
            PENDING_REQUESTS_STATE: [CallbackQueryHandler(requests_callback, pattern=r"^req_"), CallbackQueryHandler(pending_requests_callback, pattern=r"^(pend_accept:|pend_accept_all|pend_back)$")],
            TEAM_SELECTION: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, process_team_selection)],
            TEAM_MENU_STATE: [
                MessageHandler(filters.Regex(r"^📊 KPI команды$"), show_team_kpi),
                MessageHandler(filters.Regex(r"^📦 Остатки команды$"), show_team_balances),
                MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
            ],
            ISSUANCE_MENU: [MessageHandler(filters.Regex(r"^(MINTS|Стики|📥 Загрузить выдачи \(Excel\)|📊 Выгрузка статистики)$"), issuance_menu_message), MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action)],
            ISSUANCE_EXCEL_UPLOAD: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.Document.ALL, process_issuance_excel_file)],
            ISSUANCE_USER: [CallbackQueryHandler(issuance_callback, pattern=r"^(issue_(type|user):|issue_cancel)$")],
            ISSUANCE_AMOUNT: [CallbackQueryHandler(issuance_callback, pattern=r"^(issue_confirm|issue_change_user|issue_cancel)$"), MessageHandler(filters.TEXT & ~filters.COMMAND, process_issuance_amount)],
        },
        fallbacks=[
            CommandHandler("admin", enter_admin_mode),
            CommandHandler("coor", exit_admin_mode),
            MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action),
        ],
        per_chat=True,
        per_user=True,
        per_message=False,
        allow_reentry=True,
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(team_moderation_callback, pattern=r"^team_(accept|reject):"))
    app.add_handler(CallbackQueryHandler(requests_callback, pattern=r"^req_"))
    app.add_handler(MessageHandler(filters.Regex(r"^Мой KPI$"), my_kpi_menu))
    app.add_handler(MessageHandler(filters.Regex(r"^Остатки$"), show_balances))
    app.add_handler(CallbackQueryHandler(my_kpi_callback, pattern=r"^my_kpi_"))
    app.add_handler(MessageHandler(filters.Regex(r"^Справочник KPI$"), kpi_menu))
    app.add_handler(CallbackQueryHandler(kpi_callback, pattern=r"^kpi_"))
    return app
