from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from types import SimpleNamespace
from unittest.mock import AsyncMock

import handlers.admin as admin_handlers
import handlers.requests as request_handlers
import services
import storage
from organization import build_employee_registry


async def test_request_inbox() -> None:
    original_load_pending = request_handlers.load_pending

    async def fake_load_pending():
        return {"1": "Иван Иванов"}

    request_handlers.load_pending = fake_load_pending
    try:
        inbox = await request_handlers.load_request_inbox()
        assert [item["kind"] for item in inbox] == ["registration"]
        markup = request_handlers.build_requests_markup(inbox)
        callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        assert "req_accept:registration:1" in callbacks
        assert "req_accept:team:2" not in callbacks
        assert "req_accept:user:custom-1" not in callbacks
    finally:
        request_handlers.load_pending = original_load_pending


async def test_user_list_groups_and_data_sources() -> None:
    original_employee_factory = admin_handlers.EmployeeService.from_default_storage

    class FixtureRepository:
        async def load(self):
            return {"100": "Реальный Пользователь", "excel_legacy": "Сотрудник из файла"}

    class FixtureEmployeeService:
        def __init__(self):
            self.users = FixtureRepository()

        async def list_registry(self):
            return build_employee_registry(
                {"100": "Реальный Пользователь", "excel_legacy": "Сотрудник из файла"},
                {"100": {"name": "Реальный Пользователь", "group": "A LAMP"}},
                {
                    "реальный пользователь": {"original_name": "Реальный Пользователь"},
                    "новый kpi": {"original_name": "Новый KPI"},
                },
                {"_schema_version": 2, "200": {"name": "Выдача без регистрации"}},
            )

    admin_handlers.EmployeeService.from_default_storage = lambda: FixtureEmployeeService()
    try:
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=SimpleNamespace(id=admin_handlers.ADMIN_ID), message=message)
        context = SimpleNamespace(user_data={"admin_mode": True})
        result = await admin_handlers.show_registered_users(update, context)
        assert result == admin_handlers.EXTRA_MENU_STATE
        text = message.reply_text.await_args.args[0]
        assert "Все пользователи (4)" in text
        assert "✅ *Реальный Пользователь*" in text
        assert "Группа: **A LAMP**" in text
        assert "❌ *Сотрудник из файла*" in text
        assert "❌ *Новый KPI*" in text
        assert "❌ *Выдача без регистрации*" in text
        assert any(item.get("registered") is True for item in context.user_data["user_index_map"].values())
        assert any(item.get("registered") is False for item in context.user_data["user_index_map"].values())
    finally:
        admin_handlers.EmployeeService.from_default_storage = original_employee_factory


async def test_request_reminder_throttle() -> None:
    original_load_pending = services.load_pending
    original_load_json = services.load_json

    async def fake_load_pending():
        return {"1": "Иван Иванов"}

    async def fake_load_json(path):
        return {}

    services.load_pending = fake_load_pending
    services.load_json = fake_load_json
    bot = SimpleNamespace(send_message=AsyncMock())
    context = SimpleNamespace(bot=bot, application=SimpleNamespace(bot_data={}))
    try:
        await services.check_pending_requests_job(context)
        await services.check_pending_requests_job(context)
        assert bot.send_message.await_count == 1
    finally:
        services.load_pending = original_load_pending
        services.load_json = original_load_json


def test_atomic_storage() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "data.json"
        storage._sync_save_json({"ok": True}, str(path))
        assert json.loads(path.read_text(encoding="utf-8")) == {"ok": True}
        assert not path.with_name("data.json.tmp").exists()


def test_no_startup_user_cleanup() -> None:
    bot_source = (ROOT / "bot.py").read_text(encoding="utf-8")
    storage_source = (ROOT / "storage.py").read_text(encoding="utf-8")
    assert "remove_admin_registration_records" not in bot_source
    assert "remove_admin_registration_records" not in storage_source


async def test_concurrent_registration_updates() -> None:
    original_pending_file = storage.PENDING_FILE
    with tempfile.TemporaryDirectory() as directory:
        pending_path = Path(directory) / "pending.json"
        storage.PENDING_FILE = str(pending_path)
        storage._sync_save_json({}, str(pending_path))
        try:
            async def add_request(index: int):
                def mutate(data):
                    data[str(index)] = {"name": f"User {index}", "group": "R LAMP"}
                await storage.update_pending(mutate)

            await asyncio.gather(*(add_request(index) for index in range(25)))
            saved = storage._sync_load_json(str(pending_path))
            assert len(saved) == 25

            async def remove_request(index: int):
                def mutate(data):
                    return data.pop(str(index), None)
                return await storage.update_pending(mutate)

            results = await asyncio.gather(*(remove_request(index) for index in range(10)))
            assert all(result is not None for result in results)
            assert len(storage._sync_load_json(str(pending_path))) == 15
            duplicate_results = await asyncio.gather(remove_request(0), remove_request(0))
            assert sum(result is not None for result in duplicate_results) == 0
        finally:
            storage.PENDING_FILE = original_pending_file


async def main() -> None:
    await test_request_inbox()
    await test_user_list_groups_and_data_sources()
    await test_request_reminder_throttle()
    test_atomic_storage()
    test_no_startup_user_cleanup()
    await test_concurrent_registration_updates()
    print("behavior audit passed")


if __name__ == "__main__":
    asyncio.run(main())
