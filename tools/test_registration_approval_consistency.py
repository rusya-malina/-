"""Regression test for all registration approval entry points."""
from __future__ import annotations

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
from data_models import make_group_record, make_user_record


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
        "request_load_pending": request_handlers.load_pending,
        "request_service": request_handlers.RegistrationService,
        "admin_load_pending": admin_handlers.load_pending,
        "admin_show_after": admin_handlers._show_requests_after_callback,
    }

    async def run_scenario(callback_data: str, *, screen_flow: bool = False, direct_flow: bool = False) -> dict:
        saved: dict[str, dict] = {}

        class FakeRegistrationService:
            @classmethod
            def from_default_storage(cls):
                return cls()

            async def approve(self, user_id, actor_id):
                assert str(actor_id) == str(ADMIN_ID)
                saved["users"] = {str(user_id): make_user_record(request["name"])}
                saved["groups"] = {str(user_id): make_group_record(request["name"], request["group"])}
                return SimpleNamespace(
                    ok=True,
                    details={"name": request["name"], "group": request["group"]},
                )

            async def reject(self, user_id, actor_id):
                assert str(actor_id) == str(ADMIN_ID)
                saved["users"] = {}
                saved["groups"] = {}
                return SimpleNamespace(
                    ok=True,
                    details={"name": request["name"], "group": request["group"]},
                )

        request_handlers.RegistrationService = FakeRegistrationService
        request_handlers.load_pending = AsyncMock(return_value={"100": copy.deepcopy(request)})
        if direct_flow:
            request_handlers.load_request_inbox = AsyncMock(return_value=[inbox_item])
        if screen_flow:
            admin_handlers.load_pending = AsyncMock(return_value={"100": copy.deepcopy(request)})
            admin_handlers._show_requests_after_callback = AsyncMock(return_value=ConversationHandler.END)

        query = FakeQuery(callback_data)
        if screen_flow:
            result = await admin_handlers.pending_requests_callback(SimpleNamespace(callback_query=query), FakeContext())
        elif callback_data.startswith("adm_"):
            result = await admin_handlers.admin_moderation_callback(SimpleNamespace(callback_query=query), FakeContext())
        else:
            result = await request_handlers.requests_callback(SimpleNamespace(callback_query=query), FakeContext())
        assert result == ConversationHandler.END
        return saved

    try:
        direct = await run_scenario("req_accept:registration:100", direct_flow=True)
        old_screen = await run_scenario("pend_accept:100", screen_flow=True)
        legacy_notification = await run_scenario("adm_accept:100")
        for result in (direct, old_screen, legacy_notification):
            user_record = result["users"]["100"]
            assert user_record["schema_version"] == 1
            assert user_record["name"] == "Тест Пользователь"
            group_record = result["groups"]["100"]
            assert group_record["schema_version"] == 1
            assert group_record["name"] == "Тест Пользователь"
            assert group_record["group"] == "A LAMP"
        print("REGISTRATION_APPROVAL_CONSISTENCY PASS")
    finally:
        request_handlers.load_request_inbox = original["request_load_inbox"]
        request_handlers.load_pending = original["request_load_pending"]
        request_handlers.RegistrationService = original["request_service"]
        admin_handlers.load_pending = original["admin_load_pending"]
        admin_handlers._show_requests_after_callback = original["admin_show_after"]


if __name__ == "__main__":
    asyncio.run(run_consistency_test())
