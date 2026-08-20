"""Resilient Telegram polling supervisor."""
from __future__ import annotations

import signal
import threading
from collections.abc import Callable
from typing import Any

from telegram.error import Conflict, TelegramError

from bot_context import logging

POLLING_RETRY_DELAY = 15


class PollingSupervisor:
    """Owns application lifecycle and retries polling after transient failures."""

    def __init__(self, token: str, build_application: Callable[[str], Any], retry_delay: int = POLLING_RETRY_DELAY):
        self.token = token
        self.build_application = build_application
        self.retry_delay = retry_delay
        self.stop_event = threading.Event()
        self.current_app: Any | None = None

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def stop(self) -> None:
        self.stop_event.set()
        app = self.current_app
        if app is None:
            return
        try:
            app.stop_running()
        except (OSError, RuntimeError, TelegramError):
            logging.exception("Failed to stop Telegram application gracefully")

    def run(self) -> None:
        while not self.stop_event.is_set():
            app = self.build_application(self.token)
            self.current_app = app
            try:
                logging.info("Telegram bot polling attempt started")
                app.run_polling(
                    drop_pending_updates=False,
                    bootstrap_retries=5,
                    close_loop=False,
                    stop_signals=(),
                )
                if not self.stop_event.is_set():
                    logging.warning(
                        "Telegram polling stopped unexpectedly; retrying in %s seconds",
                        self.retry_delay,
                    )
            except Conflict:
                logging.warning(
                    "Telegram getUpdates conflict; another instance may still be handing over. "
                    "Retrying in %s seconds.",
                    self.retry_delay,
                )
            except (OSError, RuntimeError, TelegramError):
                logging.exception("Telegram polling stopped unexpectedly")
            finally:
                self.current_app = None

            if not self.stop_event.is_set():
                self.stop_event.wait(self.retry_delay)

    def _handle_shutdown(self, signum, _frame) -> None:
        logging.info("Shutdown signal %s received", signum)
        self.stop()


__all__ = ["POLLING_RETRY_DELAY", "PollingSupervisor"]
