"""Composition root for the Telegram bot process."""
from __future__ import annotations

from app_factory import build_application
from bot_context import logging, os
from runtime.polling_supervisor import PollingSupervisor
from runtime.startup import prepare_data, restore_external_state
from runtime.webhook_server import WebhookServer


def _webhook_config() -> tuple[str, str, str]:
    public_url = os.getenv("WEBHOOK_PUBLIC_URL") or os.getenv("RENDER_EXTERNAL_URL")
    path = os.getenv("WEBHOOK_PATH", "/telegram/webhook")
    secret = os.getenv("WEBHOOK_SECRET")
    if not public_url:
        raise RuntimeError("WEBHOOK_PUBLIC_URL или RENDER_EXTERNAL_URL не задана")
    if not secret:
        raise RuntimeError("WEBHOOK_SECRET не задан")
    public_url = public_url.rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    return public_url, path, secret


def main() -> None:
    """Restore runtime data and start exactly one Telegram transport."""
    restore_external_state()
    prepare_data()
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Переменная окружения BOT_TOKEN не задана. "
            "Добавьте её в настройках Render или локального окружения."
        )

    transport = os.getenv("TELEGRAM_TRANSPORT", "webhook").strip().lower()
    if transport == "polling":
        supervisor = PollingSupervisor(token, build_application)
        supervisor.install_signal_handlers()
        supervisor.run()
        return
    if transport != "webhook":
        raise RuntimeError(f"Неизвестный TELEGRAM_TRANSPORT: {transport}")

    public_url, path, secret = _webhook_config()
    server = WebhookServer(
        port=int(os.getenv("PORT", "10000")),
        application=build_application(token),
        path=path,
        secret=secret,
        public_url=public_url,
    )
    server.install_signal_handlers()
    try:
        server.start()
        server.wait()
    finally:
        server.close()
        logging.info("Webhook server stopped gracefully")


if __name__ == "__main__":
    main()
