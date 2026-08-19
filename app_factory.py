"""Сборка Telegram Application и маршрутизация по функциональным модулям."""
from bot_context import *
from services import check_pending_requests_job
from handlers.user import *
from handlers.admin import *
from handlers.teams import *
from handlers.kpi import *
from handlers.issuance import *
from handlers.uploads import *
from handlers.broadcast import *
from handlers.requests import *


def build_application(token: str) -> Application:
    """Создаёт приложение, подключает фоновые задачи и маршруты Telegram."""
    request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    app = Application.builder().token(token).request(request).build()

    if app.job_queue:
        app.job_queue.run_repeating(check_pending_requests_job, interval=300, first=60)

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex(r"^Новый расчет$"), new_calculation),
            MessageHandler(filters.Regex(r"^Определить команду$"), start_team_selection),
            MessageHandler(filters.Regex(r"^📢 Рассылка$"), start_broadcast),
            MessageHandler(filters.Regex(r"^Загрузить данные$"), open_kpi_admin_menu),
            MessageHandler(filters.Regex(r"^⚙️ Дополнительно$"), open_extra_menu),
            MessageHandler(filters.Regex(r"^Выдача$"), start_issuance),
            MessageHandler(filters.Regex(r"^📝 Оставить заявку$"), start_user_request),
        ],
        states={
            REG_GROUP: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, reg_get_group)],
            REG_FIRST_NAME: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, reg_get_first_name)],
            REG_LAST_NAME: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, reg_get_last_name)],
            LAS: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, get_las)],
            LAU: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, get_lau)],
            CHANGE_NAME: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_first_name)],
            CHANGE_LAST_NAME: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_full_name)],
            BROADCAST: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.PHOTO, send_broadcast), MessageHandler(filters.TEXT & ~filters.COMMAND, send_broadcast)],
            KPI_MENU_STATE: [MessageHandler(filters.Regex(r"^📥 Загрузить KPI \(Excel\)$"), start_excel_upload), MessageHandler(filters.Regex(r"^✏️ Ввести KPI вручную$"), start_manual_kpi), MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action)],
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
            USER_REQUEST: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.TEXT & ~filters.COMMAND, process_user_request)],
            ISSUANCE_MENU: [MessageHandler(filters.Regex(r"^(MINTS|Стики|📥 Загрузить выдачи \(Excel\)|📊 Выгрузка статистики)$"), issuance_menu_message), MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action)],
            ISSUANCE_EXCEL_UPLOAD: [MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action), MessageHandler(filters.Document.ALL, process_issuance_excel_file)],
            ISSUANCE_USER: [CallbackQueryHandler(issuance_callback, pattern=r"^(issue_(type|user):|issue_cancel)$")],
            ISSUANCE_AMOUNT: [CallbackQueryHandler(issuance_callback, pattern=r"^(issue_confirm|issue_change_user|issue_cancel)$"), MessageHandler(filters.TEXT & ~filters.COMMAND, process_issuance_amount)],
        },
        fallbacks=[MessageHandler(filters.Regex(r"^⬅️ Назад$"), cancel_action)],
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
