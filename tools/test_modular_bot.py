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
from bot_context import (
    EXTRA_MENU_STATE,
    PENDING_REQUESTS_STATE,
    TEAM_OPTIONS,
    ThreadingHTTPServer,
)
from handlers.requests import build_requests_markup
from health import HealthHandler
from keyboards import (
    get_data_keyboard,
    get_issuance_confirmation_markup,
    get_issuance_keyboard,
    get_kpi_menu_keyboard,
    get_main_keyboard,
    get_registration_group_keyboard,
)
from services import calculate_balances, find_telegram_user_ids_by_name

MODULES = [
    "bot_context",
    "storage",
    "organization",
    "roles",
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
    "handlers.training",
]


def main() -> None:
    for module_name in MODULES:
        importlib.import_module(module_name)

    app = build_application("123456:TEST_TOKEN")
    assert len(app.handlers) >= 1
    conversation = app.handlers[0][0]
    extra_state_handlers = conversation.states[EXTRA_MENU_STATE]
    extra_callback_patterns = {handler.pattern.pattern for handler in extra_state_handlers if hasattr(handler, "pattern")}
    assert any(pattern == r"^req_" for pattern in extra_callback_patterns)
    assert any(pattern == r"^team_(accept|reject):" for pattern in extra_callback_patterns)
    pending_state_handlers = conversation.states[PENDING_REQUESTS_STATE]
    pending_callback_patterns = {handler.pattern.pattern for handler in pending_state_handlers if hasattr(handler, "pattern")}
    assert any(pattern == r"^req_" for pattern in pending_callback_patterns)
    main_keyboard = get_main_keyboard(14599689, admin_mode=True)
    assert main_keyboard.keyboard
    admin_buttons = {button.text for row in main_keyboard.keyboard for button in row}
    assert "📝 Оставить заявку" not in admin_buttons
    assert {"Новый расчет", "Мой KPI", "Справочник KPI", "Остатки", "📦 Выдача", "Загрузить данные", "📢 Рассылка", "⚙️ Дополнительно"}.issubset(admin_buttons)
    data_buttons = {button.text for row in get_data_keyboard().keyboard for button in row}
    assert {"📥 Загрузить KPI (Excel)", "📥 Загрузить выдачи (Excel)", "📊 Выгрузка статистики"}.issubset(data_buttons)
    assert "MINTS" not in data_buttons and "Стики" not in data_buttons
    issuance_buttons = {button.text for row in get_issuance_keyboard().keyboard for button in row}
    assert {"MINTS", "Стики", "⬅️ Назад"}.issubset(issuance_buttons)
    assert "Определить команду" not in admin_buttons
    kpi_admin_buttons = {button.text for row in get_kpi_menu_keyboard().keyboard for button in row}
    assert "📥 Загрузить KPI (Excel)" in kpi_admin_buttons
    assert "✏️ Ввести KPI вручную" not in kpi_admin_buttons
    registration_keyboard = get_registration_group_keyboard()
    registration_buttons = {button.text for row in registration_keyboard.keyboard for button in row}
    assert registration_buttons == set(TEAM_OPTIONS)
    r_lamp_buttons = {button.text for row in get_main_keyboard(100, "R LAMP").keyboard for button in row}
    coor_buttons = {button.text for row in get_main_keyboard(101, "coor A").keyboard for button in row}
    spv_buttons = {button.text for row in get_main_keyboard(102, "SPV").keyboard for button in row}
    assert {"Новый расчет", "Мой KPI", "Справочник KPI", "Остатки", "Мои обучения"}.issubset(r_lamp_buttons)
    assert {"Новый расчет", "Мой KPI", "Справочник KPI", "Остатки", "Загрузить обучение", "📦 Выдача"}.issubset(coor_buttons)
    assert {"Новый расчет", "Мой KPI", "Справочник KPI"}.issubset(spv_buttons)
    assert "Остатки" not in spv_buttons
    assert "Мои обучения" not in coor_buttons
    assert "📝 Оставить заявку" not in r_lamp_buttons | coor_buttons | spv_buttons
    assert "R LAMP" in TEAM_OPTIONS
    assert "К LAMP" not in TEAM_OPTIONS
    assert get_issuance_confirmation_markup().inline_keyboard
    request_markup = build_requests_markup([{"id": "registration:1", "kind": "registration", "user_id": "1", "name": "Тест", "group": "R LAMP", "text": "Проверка"}])
    callback_values = [button.callback_data for row in request_markup.inline_keyboard for button in row]
    assert "req_accept:registration:1" in callback_values
    assert "req_reject:registration:1" in callback_values
    matched_ids = find_telegram_user_ids_by_name(
        {"100": "Анна Петрова", "excel_anna_petrova": "Анна Петрова", "101": "Иван Сидоров"},
        "  Анна   Петрова ",
    )
    assert matched_ids == [100]

    balances = calculate_balances(
        {"micro_las_fact": 2, "micro_lau_fact": 3, "gt_fact": 4},
        {"mints_issued": 10, "sticks_issued": 9},
    )
    assert balances["mints_balance"] == 5
    assert balances["sticks_balance"] == 5
    for data_name in ("users.json", "kpi_data.json"):
        data_path = ROOT / data_name
        if data_path.exists():
            data = __import__("json").loads(data_path.read_text(encoding="utf-8"))
            assert data, f"{data_name} must not be empty when present"
    assert Path("handlers/uploads.py").exists()
    assert hasattr(app_factory, "process_excel_file")
    assert hasattr(app_factory, "process_issuance_excel_file")
    assert {job.name for job in app.job_queue.jobs()} >= {"training_compliance_thursday"}
    assert not hasattr(bot, "process_excel_file")
    polling_source = (ROOT / "runtime" / "polling_supervisor.py").read_text(encoding="utf-8")
    assert "except Conflict" in polling_source
    assert "stop_signals=()" in polling_source
    assert "POLLING_RETRY_DELAY" in polling_source

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
