"""Recovery boundaries for Telegram polling and transient runtime failures."""
from __future__ import annotations

from telegram.error import Conflict, TelegramError

from bot_context import logging

POLLING_CONFLICT_FLAG = "polling_conflict_detected"


async def handle_application_error(update, context) -> None:
    """Handle polling errors without leaking task exceptions to the event loop."""
    error = context.error
    application = context.application
    if isinstance(error, Conflict):
        logging.warning(
            "Telegram getUpdates conflict detected; stopping current application "
            "so the outer polling supervisor can recover: %s",
            error,
        )
        application.bot_data[POLLING_CONFLICT_FLAG] = True
        try:
            application.stop_running()
        except (OSError, RuntimeError, TelegramError):
            logging.exception("Failed to stop application after Telegram polling conflict")
        return

    if isinstance(error, TelegramError):
        logging.error("Telegram application error: %s", error)
        return

    logging.exception("Unhandled application error: %s", error)


__all__ = ["POLLING_CONFLICT_FLAG", "handle_application_error"]
