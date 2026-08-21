"""Tests for KPI Excel notification delivery."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import services


async def main() -> None:
    original_load = services.load_json
    users = {
        "5150364549": {"name": "Елена Синько"},
        "excel_новый сотрудник": {"name": "Новый сотрудник"},
    }

    async def load_json(_path: str):
        return users

    try:
        services.load_json = load_json
        context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
        result = await services.notify_users_kpi_updated(
            context,
            ["Елена   Синько", "Новый сотрудник", "Неизвестный сотрудник", "Елена Синько"],
        )
        assert result == {"sent": 1, "failed": 0, "unmatched": 2}
        context.bot.send_message.assert_awaited_once()
        call = context.bot.send_message.await_args
        assert call.kwargs["chat_id"] == 5150364549
        assert "Елена Синько" in call.kwargs["text"]
        assert "Мой KPI" in call.kwargs["text"]
    finally:
        services.load_json = original_load

    print("KPI_NOTIFICATIONS PASS")


if __name__ == "__main__":
    asyncio.run(main())
