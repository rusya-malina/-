from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handlers.issuance as handler
from bot_context import ISSUANCE_MENU
from domain.models import OperationResult
from config import USERS_FILE


async def main() -> None:
    original_load_json = handler.load_json
    original_allowed = handler._target_is_allowed
    original_service_factory = handler.IssuanceService.from_default_storage
    try:
        async def fake_load_json(path):
            if path == USERS_FILE:
                return {"101": "Сотрудник A"}
            raise AssertionError(path)

        async def fake_allowed(*_args, **_kwargs):
            return True

        class FakeService:
            async def issue(self, *_args, **_kwargs):
                return OperationResult(True, "issued", "issuance_saved", ("101",), {"total": 7.0})

        handler.load_json = fake_load_json
        handler._target_is_allowed = fake_allowed
        handler.IssuanceService.from_default_storage = classmethod(lambda cls: FakeService())

        query = SimpleNamespace(
            from_user=SimpleNamespace(id=5001),
            message=SimpleNamespace(edit_text=AsyncMock(), chat_id=5001),
        )
        context = SimpleNamespace(user_data={
            "issuance_user_id": "101",
            "issuance_type": "sticks",
            "issuance_amount": 7.0,
        }, bot=SimpleNamespace(send_message=AsyncMock()))
        update = SimpleNamespace(callback_query=query)
        result = await handler.confirm_issuance(update, context)
        assert result == ISSUANCE_MENU
        assert context.user_data == {}
        assert context.bot.send_message.await_count == 1
        assert context.bot.send_message.await_args.kwargs["reply_markup"].keyboard
        assert "следующую выдачу" in context.bot.send_message.await_args.kwargs["text"]
    finally:
        handler.load_json = original_load_json
        handler._target_is_allowed = original_allowed
        handler.IssuanceService.from_default_storage = original_service_factory


if __name__ == "__main__":
    asyncio.run(main())
    print("REPEATED_ISSUANCE_FLOW PASS")
