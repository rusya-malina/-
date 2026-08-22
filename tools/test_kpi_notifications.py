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


async def test_manager_notification() -> None:
    original_load = services.load_json
    users = {
        "101": {"name": "Coordinator A"},
        "102": {"name": "Supervisor"},
        "103": {"name": "Manager"},
        "excel_employee": {"name": "Excel Employee"},
    }
    groups = {
        "101": {"name": "Coordinator A", "group": "coor A"},
        "102": {"name": "Supervisor", "group": "SPV"},
        "103": {"name": "Manager", "group": "MNG"},
        "excel_employee": {"name": "Excel Employee", "group": "A LAMP"},
    }

    async def load_json(path: str):
        return users if path == services.USERS_FILE else groups

    try:
        services.load_json = load_json
        context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
        result = await services.notify_managers_team_kpi_recalculated(context)
        assert result == {"sent": 3, "failed": 0, "unmatched": 0}
        assert context.bot.send_message.await_count == 3
        texts = [call.kwargs["text"] for call in context.bot.send_message.await_args_list]
        assert all("Загружен новый файл KPI" in text for text in texts)
        assert all("перерасчитаны" in text for text in texts)
        assert all("Мои KPI" in text for text in texts)
    finally:
        services.load_json = original_load


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

    await test_manager_notification()
    print("KPI_NOTIFICATIONS PASS")


if __name__ == "__main__":
    asyncio.run(main())
