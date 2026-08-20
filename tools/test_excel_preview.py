"""Regression tests for staged Excel preview and confirmation callbacks."""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handlers.uploads as uploads
from bot_context import ADMIN_ID, ISSUANCE_MENU, KPI_MENU_STATE


class FakeQuery:
    def __init__(self, data: str):
        self.data = data
        self.from_user = SimpleNamespace(id=ADMIN_ID)
        self.message = SimpleNamespace(chat_id=ADMIN_ID, edit_text=AsyncMock())
        self.answer = AsyncMock()


class FakeContext:
    def __init__(self, staged: dict):
        self.user_data = {"admin_mode": True, "pending_excel_import": staged}
        self.bot = SimpleNamespace(send_message=AsyncMock())


async def test_cancel_kpi_preview() -> None:
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_path = temp_file.name
    context = FakeContext({"kind": "kpi", "temp_path": temp_path})
    query = FakeQuery("excel_cancel")
    result = await uploads.excel_preview_callback(SimpleNamespace(callback_query=query), context)
    assert result == KPI_MENU_STATE
    assert not Path(temp_path).exists()
    assert "pending_excel_import" not in context.user_data
    assert "отменён" in query.message.edit_text.await_args.args[0]
    assert context.bot.send_message.await_count == 1


async def test_confirm_kpi_preview_does_not_rewrite_callback_contract() -> None:
    original_apply = uploads._apply_kpi_import
    apply_mock = AsyncMock()
    uploads._apply_kpi_import = apply_mock
    try:
        context = FakeContext({"kind": "kpi", "temp_path": None, "row_count": 2})
        query = FakeQuery("excel_confirm")
        result = await uploads.excel_preview_callback(SimpleNamespace(callback_query=query), context)
        assert result == KPI_MENU_STATE
        assert apply_mock.await_count == 1
        assert "pending_excel_import" not in context.user_data
        assert "подтверждён" in query.message.edit_text.await_args.args[0]
    finally:
        uploads._apply_kpi_import = original_apply


async def test_cancel_issuance_preview_returns_issuance_menu() -> None:
    context = FakeContext({"kind": "issuance", "temp_path": None})
    query = FakeQuery("excel_cancel")
    result = await uploads.excel_preview_callback(SimpleNamespace(callback_query=query), context)
    assert result == ISSUANCE_MENU
    assert "pending_excel_import" not in context.user_data


def test_preview_markup() -> None:
    callbacks = [
        button.callback_data
        for row in uploads._excel_preview_markup().inline_keyboard
        for button in row
    ]
    assert callbacks == ["excel_confirm", "excel_cancel"]


async def main() -> None:
    await test_cancel_kpi_preview()
    await test_confirm_kpi_preview_does_not_rewrite_callback_contract()
    await test_cancel_issuance_preview_returns_issuance_menu()
    test_preview_markup()
    print("EXCEL_PREVIEW PASS")


if __name__ == "__main__":
    asyncio.run(main())
