"""Recovery boundaries for Telegram polling and transient runtime failures."""
from __future__ import annotations

from telegram.error import Conflict, TelegramError

from bot_context import logging


async def handle_application_error(update, context) -> None:
    """Restarts polling after a Telegram getUpdates conflict.

    PTB delivers polling errors through ``Application.process_error``. Without
    an error handler, a Conflict is only logged inside the running application,
    so the outer retry loop in bot.py never gets a chance to recreate polling.
    Stopping the current application lets bot.py wait and start a fresh one.
    """
    error = context.error
    if isinstance(error, Conflict):
        logging.warning(
            "Telegram getUpdates conflict detected; stopping current application "
            "so the outer polling supervisor can recover: %s",
            error,
        )
        context.application.stop_running()
        return

    if isinstance(error, TelegramError):
        logging.error("Telegram application error: %s", error)
        return

    logging.exception("Unhandled application error: %s", error)


__all__ = ["handle_application_error"]
