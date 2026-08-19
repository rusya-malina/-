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

import handlers.requests as request_handlers
import services
import storage


async def test_request_inbox() -> None:
    original_load_pending = request_handlers.load_pending
    original_load_json = request_handlers.load_json

    async def fake_load_pending():
        return {"1": "Иван Иванов"}

    async def fake_load_json(path):
        if path == request_handlers.TEAM_REQUESTS_FILE:
            return {"2": {"name": "Пётр Петров", "team": "R LAMP", "created_at": "2026-01-01T00:00:00+00:00"}}
        if path == request_handlers.USER_REQUESTS_FILE:
            return {"custom-1": {"user_id": "3", "name": "Анна", "text": "Нужна справка", "created_at": "2026-01-02T00:00:00+00:00"}}
        return {}

    request_handlers.load_pending = fake_load_pending
    request_handlers.load_json = fake_load_json
    try:
        inbox = await request_handlers.load_request_inbox()
        assert [item["kind"] for item in inbox] == ["registration", "team", "user"]
        markup = request_handlers.build_requests_markup(inbox)
        callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        assert "req_accept:registration:1" in callbacks
        assert "req_accept:team:2" in callbacks
        assert "req_accept:user:custom-1" in callbacks
    finally:
        request_handlers.load_pending = original_load_pending
        request_handlers.load_json = original_load_json


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


def test_admin_registration_cleanup() -> None:
    original_registration_files = storage._registration_files
    with tempfile.TemporaryDirectory() as directory:
        paths = tuple(str(Path(directory) / f"registration_{index}.json") for index in range(6))
        for path in paths:
            storage._sync_save_json({str(storage.ADMIN_ID): {"name": "Администратор"}, "other": 1}, path)
        storage._registration_files = lambda: paths
        try:
            removed = storage.remove_admin_registration_records_sync()
            assert sum(removed.values()) == 6
            for path in paths:
                assert storage._sync_load_json(path) == {"other": 1}
        finally:
            storage._registration_files = original_registration_files


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
    await test_request_reminder_throttle()
    test_atomic_storage()
    test_admin_registration_cleanup()
    await test_concurrent_registration_updates()
    print("behavior audit passed")


if __name__ == "__main__":
    asyncio.run(main())
