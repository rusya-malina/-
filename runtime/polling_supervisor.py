"""Resilient Telegram polling supervisor."""
from __future__ import annotations

import random
import signal
import threading
import time
from collections.abc import Callable
from typing import Any

from telegram.error import Conflict, TelegramError

from bot_context import logging

POLLING_RETRY_DELAY = 15
POLLING_MAX_RETRY_DELAY = 120
POLLING_RETRY_JITTER = 3
POLLING_STABLE_SECONDS = 60


class PollingSupervisor:
    """Own one application lifecycle and retry polling sequentially."""

    def __init__(
        self,
        token: str,
        build_application: Callable[[str], Any],
        retry_delay: int = POLLING_RETRY_DELAY,
        max_retry_delay: int = POLLING_MAX_RETRY_DELAY,
        jitter: int = POLLING_RETRY_JITTER,
    ):
        self.token = token
        self.build_application = build_application
        self.retry_delay = max(0, retry_delay)
        self.max_retry_delay = max(self.retry_delay, max_retry_delay)
        self.jitter = max(0, jitter)
        self.stop_event = threading.Event()
        self.current_app: Any | None = None
        self._run_lock = threading.Lock()

    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def stop(self) -> None:
        """Request shutdown and stop the current polling application."""
        self.stop_event.set()
        app = self.current_app
        if app is None:
            return
        try:
            app.stop_running()
            logging.info("Telegram polling stop requested")
        except (OSError, RuntimeError, TelegramError):
            logging.exception("Failed to stop Telegram application gracefully")

    def run(self) -> None:
        """Run one supervisor loop; never create overlapping polling cycles."""
        if not self._run_lock.acquire(blocking=False):
            logging.error("Telegram polling supervisor is already running; refusing duplicate loop")
            return

        retry_delay = self.retry_delay
        try:
            while not self.stop_event.is_set():
                app = self.build_application(self.token)
                self.current_app = app
                started_at = time.monotonic()
                try:
                    logging.info("Telegram polling attempt started")
                    app.run_polling(
                        drop_pending_updates=False,
                        bootstrap_retries=5,
                        close_loop=False,
                        stop_signals=(),
                    )
                    if not self.stop_event.is_set():
                        logging.warning(
                            "Telegram polling stopped unexpectedly; retrying in %s seconds",
                            retry_delay,
                        )
                except Conflict as error:
                    logging.warning(
                        "Telegram getUpdates conflict; another instance may still be handing over: %s",
                        error,
                    )
                except (OSError, RuntimeError, TelegramError):
                    logging.exception("Telegram polling stopped unexpectedly")
                finally:
                    self.current_app = None
                    logging.info("Telegram polling cycle finished")

                if self.stop_event.is_set():
                    break

                uptime = time.monotonic() - started_at
                if uptime >= POLLING_STABLE_SECONDS:
                    retry_delay = self.retry_delay
                else:
                    retry_delay = min(max(retry_delay * 2, self.retry_delay), self.max_retry_delay)
                wait_for = retry_delay + random.uniform(0, self.jitter)
                logging.info("Telegram polling retry scheduled in %.1f seconds", wait_for)
                self.stop_event.wait(wait_for)
        finally:
            self._run_lock.release()
            logging.info("Telegram polling supervisor stopped")

    def _handle_shutdown(self, signum, _frame) -> None:
        logging.info("Shutdown signal %s received", signum)
        self.stop()


__all__ = [
    "POLLING_MAX_RETRY_DELAY",
    "POLLING_RETRY_DELAY",
    "POLLING_RETRY_JITTER",
    "POLLING_STABLE_SECONDS",
    "PollingSupervisor",
]
