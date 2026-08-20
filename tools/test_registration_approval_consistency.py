import asyncio
import copy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handlers.admin as admin_handlers
import handlers.requests as request_handlers
from bot_context import ADMIN_ID, ConversationHandler


class FakeMessage:
    def __init__(self):
        self.chat_id = ADMIN_ID
        self.edit_text = AsyncMock()
        self.delete = AsyncMock()


class FakeQuery:
    def __init__(self, data: str):
        self.data = data
        self.from_user = SimpleNamespace(id=ADMIN_ID)
        self.message = FakeMessage()
        self.answer = AsyncMock()


class FakeContext:
    def __init__(self):
        self.user_data = {"admin_mode": True}
        self.bot = SimpleNamespace(send_message=AsyncMock())


async def run_consistency_test() -> None:
    request = {
        "name": "Тест Пользователь",
        "group": "A LAMP",
        "created_at": "2026-08-21T00:00:00+00:00",
    }
    inbox_item = {
        "id": "registration:100",
        "kind": "registration",
        "user_id": "100",
        "name": request["name"],
        "group": request["group"],
        "text": "Выбранная группа: A LAMP.",
    }
    original = {
        "request_load_inbox": request_handlers.load_request_inbox,
        "request_update_pending": request_handlers.update_pending,
        "request_load_json": request_handlers.load_json,
        "request_save_json": request_handlers.save_json,
        "admin_load_pending": admin_handlers.load_pending,
        "admin_show_after": admin_handlers._show_requests_after_callback,
    }

    async def fake_load_json(path):
        if path == request_handlers.USERS_FILE:
            return {}
        if path == request_handlers.GROUPS_FILE:
            return {}
        return {}

    async def run_direct_button():
        saved = {}

        async def save_json(data, path):
            saved[path] = copy.deepcopy(data)

        request_handlers.load_request_inbox = AsyncMock(return_value=[inbox_item])
        request_handlers.update_pending = AsyncMock(return_value=request.copy())
        request_handlers.load_json = fake_load_json
        request_handlers.save_json = save_json
        query = FakeQuery("req_accept:registration:100")
        result = await request_handlers.requests_callback(SimpleNamespace(callback_query=query), FakeContext())
        assert result == ConversationHandler.END
        return {
            "users": saved[request_handlers.USERS_FILE],
            "groups": saved[request_handlers.GROUPS_FILE],
        }

    async def run_legacy_notification_button():
        saved = {}

        async def save_json(data, path):
            saved[path] = copy.deepcopy(data)

        request_handlers.load_request_inbox = AsyncMock(return_value=[inbox_item])
        request_handlers.update_pending = AsyncMock(return_value=request.copy())
        request_handlers.load_json = fake_load_json
        request_handlers.save_json = save_json
        query = FakeQuery("adm_accept:100")
        result = await admin_handlers.admin_moderation_callback(SimpleNamespace(callback_query=query), FakeContext())
        assert result == ConversationHandler.END
        return {
            "users": saved[request_handlers.USERS_FILE],
            "groups": saved[request_handlers.GROUPS_FILE],
        }

    async def run_old_screen_button():
        saved = {}

        async def save_json(data, path):
            saved[path] = copy.deepcopy(data)

        request_handlers.update_pending = AsyncMock(return_value=request.copy())
        request_handlers.load_json = fake_load_json
        request_handlers.save_json = save_json
        admin_handlers.load_pending = AsyncMock(return_value={"100": request.copy()})
        admin_handlers._show_requests_after_callback = AsyncMock(return_value=ConversationHandler.END)
        query = FakeQuery("pend_accept:100")
        result = await admin_handlers.pending_requests_callback(query and SimpleNamespace(callback_query=query), FakeContext())
        assert result == ConversationHandler.END
        return {
            "users": saved[request_handlers.USERS_FILE],
            "groups": saved[request_handlers.GROUPS_FILE],
        }

    try:
        direct = await run_direct_button()
        old_screen = await run_old_screen_button()
        legacy_notification = await run_legacy_notification_button()
        assert direct["users"] == old_screen["users"] == legacy_notification["users"] == {"100": "Тест Пользователь"}
        for result in (direct, old_screen, legacy_notification):
            group_record = result["groups"]["100"]
            assert group_record["name"] == "Тест Пользователь"
            assert group_record["group"] == "A LAMP"
        print("REGISTRATION_APPROVAL_CONSISTENCY PASS")
    finally:
        request_handlers.load_request_inbox = original["request_load_inbox"]
        request_handlers.update_pending = original["request_update_pending"]
        request_handlers.load_json = original["request_load_json"]
        request_handlers.save_json = original["request_save_json"]
        admin_handlers.load_pending = original["admin_load_pending"]
        admin_handlers._show_requests_after_callback = original["admin_show_after"]


if __name__ == "__main__":
    asyncio.run(run_consistency_test())
