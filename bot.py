"""Точка запуска Telegram-бота и Render health endpoint."""
import signal

from bot_context import ThreadingHTTPServer, logging, os, threading
from app_factory import build_application
from health import HealthHandler
from storage import _migrate_team_label, _reset_issuance_if_legacy
from telegram.error import Conflict


POLLING_RETRY_DELAY = 15


def main() -> None:
    """Запускает health endpoint и устойчивый Telegram polling в одном процессе Render."""
    _reset_issuance_if_legacy()
    _migrate_team_label()
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Переменная окружения BOT_TOKEN не задана. "
            "Добавьте её в настройках Render или локального окружения."
        )

    port = int(os.getenv("PORT", "10000"))
    health_server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    health_thread = threading.Thread(target=health_server.serve_forever, daemon=True)
    health_thread.start()

    stop_event = threading.Event()
    current_app = {"value": None}

    def handle_shutdown(signum, _frame):
        logging.info("Shutdown signal %s received", signum)
        stop_event.set()
        app = current_app.get("value")
        if app is not None:
            try:
                app.stop_running()
            except Exception:
                logging.exception("Failed to stop Telegram application gracefully")

    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, handle_shutdown)

    try:
        while not stop_event.is_set():
            app = build_application(token)
            current_app["value"] = app
            try:
                logging.info("Telegram bot polling attempt started")
                app.run_polling(
                    drop_pending_updates=False,
                    bootstrap_retries=5,
                    close_loop=False,
                    stop_signals=(),
                )
                if not stop_event.is_set():
                    logging.warning(
                        "Telegram polling stopped unexpectedly; retrying in %s seconds",
                        POLLING_RETRY_DELAY,
                    )
            except Conflict:
                logging.warning(
                    "Telegram getUpdates conflict; another instance may still be handing over. "
                    "Retrying in %s seconds.",
                    POLLING_RETRY_DELAY,
                )
            except Exception:
                logging.exception("Telegram polling stopped unexpectedly")
            finally:
                current_app["value"] = None

            if not stop_event.is_set():
                stop_event.wait(POLLING_RETRY_DELAY)
    finally:
        health_server.shutdown()
        health_server.server_close()
        logging.info("Health server stopped gracefully")


if __name__ == "__main__":
    main()
