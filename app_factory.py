"""Application composition root for the Telegram bot."""
from __future__ import annotations

from bot_context import Application, CallbackQueryHandler, HTTPXRequest, MessageHandler, filters
from handlers.kpi import kpi_callback, kpi_menu, my_kpi_callback, my_kpi_menu, show_balances
from handlers.requests import requests_callback
from handlers.teams import team_moderation_callback
from handlers.uploads import process_excel_file, process_issuance_excel_file  # noqa: F401
from presentation.router import build_conversation_handler
from recovery import handle_application_error
from services import check_pending_requests_job


def build_application(token: str) -> Application:
    """Create the Telegram application and attach routes/background jobs."""
    request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    app = Application.builder().token(token).request(request).build()
    app.add_error_handler(handle_application_error)

    if app.job_queue:
        app.job_queue.run_repeating(check_pending_requests_job, interval=300, first=60)

    app.add_handler(build_conversation_handler())
    app.add_handler(CallbackQueryHandler(team_moderation_callback, pattern=r"^team_(accept|reject):"))
    app.add_handler(CallbackQueryHandler(requests_callback, pattern=r"^req_"))
    app.add_handler(MessageHandler(filters.Regex(r"^Мой KPI$"), my_kpi_menu))
    app.add_handler(MessageHandler(filters.Regex(r"^Остатки$"), show_balances))
    app.add_handler(CallbackQueryHandler(my_kpi_callback, pattern=r"^my_kpi_"))
    app.add_handler(MessageHandler(filters.Regex(r"^Справочник KPI$"), kpi_menu))
    app.add_handler(CallbackQueryHandler(kpi_callback, pattern=r"^kpi_"))
    return app


__all__ = ["build_application"]
