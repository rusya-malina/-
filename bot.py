"""Composition root for the Telegram bot process."""
from __future__ import annotations

from app_factory import build_application
from bot_context import logging, os
from runtime.health_server import HealthServer
from runtime.polling_supervisor import PollingSupervisor
from runtime.startup import prepare_data, restore_external_state


def main() -> None:
    """Restore runtime data, prepare schemas, expose health and supervise polling."""
    restore_external_state()
    prepare_data()
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError(
            "Переменная окружения BOT_TOKEN не задана. "
            "Добавьте её в настройках Render или локального окружения."
        )

    health_server = HealthServer(int(os.getenv("PORT", "10000")))
    health_server.start()
    supervisor = PollingSupervisor(token, build_application)
    supervisor.install_signal_handlers()
    try:
        supervisor.run()
    finally:
        health_server.close()
        logging.info("Health server stopped gracefully")


if __name__ == "__main__":
    main()
