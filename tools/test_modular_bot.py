from __future__ import annotations

import importlib
import sys
import threading
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app_factory
import bot
from app_factory import build_application
from bot_context import TEAM_OPTIONS, ThreadingHTTPServer
from handlers.requests import build_requests_markup
from keyboards import get_issuance_confirmation_markup, get_main_keyboard
from health import HealthHandler
from services import calculate_balances


MODULES = [
    "bot_context",
    "storage",
    "keyboards",
    "services",
    "health",
    "app_factory",
    "handlers.user",
    "handlers.admin",
    "handlers.teams",
    "handlers.kpi",
    "handlers.issuance",
    "handlers.uploads",
    "handlers.broadcast",
    "handlers.requests",
]


def main() -> None:
    for module_name in MODULES:
        importlib.import_module(module_name)

    app = build_application("123456:TEST_TOKEN")
    assert len(app.handlers) >= 1
    main_keyboard = get_main_keyboard(14599689)
    assert main_keyboard.keyboard
    assert any(button.text == "📝 Оставить заявку" for row in main_keyboard.keyboard for button in row)
    assert "R LAMP" in TEAM_OPTIONS
    assert "К LAMP" not in TEAM_OPTIONS
    assert get_issuance_confirmation_markup().inline_keyboard
    request_markup = build_requests_markup([{"id": "team:1", "kind": "team", "user_id": "1", "name": "Тест", "team": "R LAMP", "text": "Проверка"}])
    callback_values = [button.callback_data for row in request_markup.inline_keyboard for button in row]
    assert "req_accept:team:1" in callback_values
    assert "req_reject:team:1" in callback_values
    balances = calculate_balances(
        {"micro_las_fact": 2, "micro_lau_fact": 3, "gt_fact": 4},
        {"mints_issued": 10, "sticks_issued": 9},
    )
    assert balances["mints_balance"] == 5
    assert balances["sticks_balance"] == 5
    assert Path("handlers/uploads.py").exists()
    assert hasattr(app_factory, "process_excel_file")
    assert hasattr(app_factory, "process_issuance_excel_file")
    assert not hasattr(bot, "process_excel_file")
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
    assert "except Conflict" in bot_source
    assert "stop_signals=()" in bot_source
    assert "POLLING_RETRY_DELAY" in bot_source

    server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/healthz"
        with urllib.request.urlopen(url, timeout=3) as response:
            assert response.status == 200
            assert response.read() == b"OK"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    print("modular smoke tests passed")


if __name__ == "__main__":
    main()
