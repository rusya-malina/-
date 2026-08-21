"""Regression tests for safe admin delete-by-number flow."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handlers.admin as admin


async def main() -> None:
    original_permission = admin.has_permission
    original_notify = admin.notify_user_bot_stopped
    original_service = admin.EmployeeAdminService

    class FailedService:
        async def delete_registered(self, _employee_id, _actor_id):
            return SimpleNamespace(ok=False)

    class SuccessfulService:
        async def delete_registered(self, _employee_id, _actor_id):
            return SimpleNamespace(ok=True)

    try:
        admin.has_permission = lambda *_args: True
        admin.notify_user_bot_stopped = AsyncMock()
        admin.EmployeeAdminService = SimpleNamespace(from_default_storage=lambda: FailedService())
        context = SimpleNamespace(user_data={"user_index_map": {1: {"uid": "123", "name": "Employee One"}}})
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=1),
            message=SimpleNamespace(text="1", reply_text=AsyncMock()),
        )
        await admin.process_delete_user_by_number(update, context)
        admin.notify_user_bot_stopped.assert_not_awaited()

        admin.notify_user_bot_stopped = AsyncMock()
        admin.EmployeeAdminService = SimpleNamespace(from_default_storage=lambda: SuccessfulService())
        context = SimpleNamespace(user_data={"user_index_map": {1: {"uid": "123", "name": "Employee One"}}})
        update.message.reply_text = AsyncMock()
        await admin.process_delete_user_by_number(update, context)
        admin.notify_user_bot_stopped.assert_awaited_once_with(context, "123")

        admin.has_permission = lambda *_args: False
        context = SimpleNamespace(user_data={"user_index_map": {1: {"uid": "123", "name": "Employee One"}}})
        update.message.reply_text = AsyncMock()
        result = await admin.process_delete_user_by_number(update, context)
        assert result == admin.ConversationHandler.END
        assert "нет доступа" in update.message.reply_text.await_args.args[0]
    finally:
        admin.has_permission = original_permission
        admin.notify_user_bot_stopped = original_notify
        admin.EmployeeAdminService = original_service

    print("ADMIN_DELETE_FLOW PASS")


if __name__ == "__main__":
    asyncio.run(main())
