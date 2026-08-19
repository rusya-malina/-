from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handlers.teams as teams_handler
from bot_context import ConversationHandler, TEAM_MENU_STATE
from keyboards import get_main_keyboard
from organization import get_scope_groups, get_visible_users


async def test_scope_and_team_view() -> None:
    assert get_scope_groups("MNG") == {"A LAMP", "R LAMP", "coor A", "coor R", "SPV", "MNG"}
    assert get_scope_groups("SPV") == {"A LAMP", "R LAMP", "coor A", "coor R", "SPV"}
    assert get_scope_groups("coor A") == {"A LAMP", "coor A"}
    assert get_scope_groups("coor R") == {"R LAMP", "coor R"}

    users = {"10": "Coor A", "11": "A User", "12": "R User", "13": "SPV User"}
    groups = {
        "10": {"group": "coor A"},
        "11": {"group": "A LAMP"},
        "12": {"group": "R LAMP"},
        "13": {"group": "SPV"},
    }
    visible = get_visible_users(10, users, groups, exclude_user_id=10)
    assert [item["user_id"] for item in visible] == ["11"]
    assert "10" not in {item["user_id"] for item in visible}
    assert "12" not in {item["user_id"] for item in visible}

    coor_buttons = {button.text for row in get_main_keyboard(10, "coor A").keyboard for button in row}
    lamp_buttons = {button.text for row in get_main_keyboard(11, "A LAMP").keyboard for button in row}
    assert "Моя команда" in coor_buttons
    assert "Моя команда" not in lamp_buttons

    original_group = teams_handler.get_user_group
    original_load_json = teams_handler.load_json
    teams_handler.get_user_group = AsyncMock(return_value="coor A")

    async def fake_load_json(path):
        if path == teams_handler.USERS_FILE:
            return users
        if path == teams_handler.GROUPS_FILE:
            return groups
        if path == teams_handler.KPI_FILE:
            return {
                "a user": {
                    "original_name": "A User",
                    "gt_plan": 100,
                    "gt_fact": 80,
                    "micro_plan": 100,
                    "micro_las_fact": 40,
                    "micro_lau_fact": 30,
                    "retrafic_plan": 100,
                    "retrafic_fact": 75,
                },
                "r user": {
                    "original_name": "R User",
                    "gt_plan": 100,
                    "gt_fact": 99,
                },
            }
        if path == teams_handler.ISSUANCE_FILE:
            return {"_schema_version": 2}
        return {}

    teams_handler.load_json = fake_load_json
    try:
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(effective_user=SimpleNamespace(id=10), message=message)
        context = SimpleNamespace(user_data={})
        result = await teams_handler.show_team_kpi(update, context)
        assert result == TEAM_MENU_STATE
        text = message.reply_text.await_args.args[0]
        assert "A User" in text
        assert "R User" not in text
        assert "KPI команды" in text
        assert "ID:" not in text and "Re-trafic: 75%" in text

        message.reply_text.reset_mock()
        result = await teams_handler.show_team_balances(update, context)
        assert result == TEAM_MENU_STATE
        balance_text = message.reply_text.await_args.args[0]
        assert "A User" in balance_text
        assert "R User" not in balance_text
        assert "Остатки команды" in balance_text
        assert "Остаток MINTS" in balance_text
        assert "GT:" not in balance_text
    finally:
        teams_handler.get_user_group = original_group
        teams_handler.load_json = original_load_json


async def main() -> None:
    await test_scope_and_team_view()
    print("hierarchy tests passed")


if __name__ == "__main__":
    asyncio.run(main())
