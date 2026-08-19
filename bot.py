"""Точка запуска Telegram-бота и Render health endpoint."""
from bot_context import ThreadingHTTPServer, logging, os, threading
from app_factory import build_application
from health import HealthHandler
from storage import _migrate_team_label, _reset_issuance_if_legacy


def main() -> None:
    """Запускает HTTP health endpoint и Telegram polling в одном процессе Render."""
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

    app = build_application(token)
    logging.info("Telegram bot started with modular handlers")
    try:
        app.run_polling(
            drop_pending_updates=False,
            bootstrap_retries=5,
        )
    finally:
        health_server.shutdown()
        health_server.server_close()
        logging.info("Health server stopped gracefully")


if __name__ == "__main__":
    main()
