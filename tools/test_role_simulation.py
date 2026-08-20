from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handlers.kpi as kpi_handler
import handlers.teams as teams_handler
from bot_context import ADMIN_ID, TEAM_MENU_STATE


USERS = {
    "101": "A One",
    "102": "R One",
    "103": "Coor A",
    "104": "Coor R",
    "105": "SPV One",
    "106": "MNG One",
    str(ADMIN_ID): "Admin User",
}
GROUPS = {
    "101": {"group": "A LAMP"},
    "102": {"group": "R LAMP"},
    "103": {"group": "coor A"},
    "104": {"group": "coor R"},
    "105": {"group": "SPV"},
    "106": {"group": "MNG"},
    str(ADMIN_ID): {"group": "coor R"},
}
KPI = {
    name.lower(): {
        "original_name": name,
        "gt_plan": 100,
        "gt_fact": 80,
        "micro_plan": 100,
        "micro_las_fact": 40,
        "micro_lau_fact": 30,
        "retrafic_plan": 100,
        "retrafic_fact": 75,
        "office_hours": 10,
        "field_hours": 5,
    }
    for name in USERS.values()
}
ISSUANCE = {
    str(user_id): {
        "name": name,
        "mints_issued": 10,
        "sticks_issued": 10,
        "history": [],
    }
    for user_id, name in USERS.items()
}


def update_for(user_id: int, text: str = ""):
    message = SimpleNamespace(reply_text=AsyncMock(), text=text)
    return SimpleNamespace(effective_user=SimpleNamespace(id=user_id), message=message)


async def main() -> None:
    original_team_group = teams_handler.get_user_group
    original_team_load = teams_handler.load_json
    original_kpi_group = kpi_handler.get_user_group
    original_kpi_load = kpi_handler.load_json

    async def team_load(path):
        if path == teams_handler.USERS_FILE:
            return USERS
        if path == teams_handler.GROUPS_FILE:
            return GROUPS
        if path == teams_handler.KPI_FILE:
            return KPI
        if path == teams_handler.ISSUANCE_FILE:
            return ISSUANCE
        return {}

    async def kpi_load(path):
        if path == kpi_handler.USERS_FILE:
            return USERS
        if path == kpi_handler.KPI_FILE:
            return KPI
        return {}

    try:
        teams_handler.load_json = team_load
        kpi_handler.load_json = kpi_load

        role_cases = [
            (101, "A LAMP", False),
            (102, "R LAMP", False),
            (103, "coor A", False),
            (104, "coor R", False),
            (105, "SPV", False),
            (106, "MNG", False),
            (ADMIN_ID, "coor R", True),
        ]
        for user_id, group, admin_mode in role_cases:
            teams_handler.get_user_group = AsyncMock(return_value=group)
            kpi_handler.get_user_group = AsyncMock(return_value=group)
            context = SimpleNamespace(user_data={"admin_mode": admin_mode})

            kpi_update = update_for(user_id)
            await kpi_handler.my_kpi_menu(kpi_update, context)
            kpi_markup = kpi_update.message.reply_text.await_args.kwargs["reply_markup"]
            kpi_buttons = {button.text for row in kpi_markup.inline_keyboard for button in row}
            assert "📊 KPI" in kpi_buttons

            query = SimpleNamespace(
                data="my_kpi_show_kpi",
                from_user=SimpleNamespace(id=user_id),
                answer=AsyncMock(),
                message=SimpleNamespace(edit_text=AsyncMock()),
            )
            callback_update = SimpleNamespace(callback_query=query)
            await kpi_handler.my_kpi_callback(callback_update, context)
            personal_text = query.message.edit_text.await_args.args[0]
            assert "Re-trafic" in personal_text
            assert "75.0%" in personal_text

            if group in {"coor A", "coor R", "SPV", "MNG"} or admin_mode:
                team_update = update_for(user_id)
                assert await teams_handler.open_my_team_menu(team_update, context) == TEAM_MENU_STATE
                assert "Моя команда" in team_update.message.reply_text.await_args.args[0]

                team_update.message.reply_text.reset_mock()
                assert await teams_handler.show_team_kpi(team_update, context) == TEAM_MENU_STATE
                team_kpi_text = team_update.message.reply_text.await_args.args[0]
                assert "Re-trafic: 75%" in team_kpi_text
                assert "ID:" not in team_kpi_text
                if admin_mode:
                    assert "Admin User" not in team_kpi_text
                if group in {"SPV", "MNG"} or admin_mode:
                    assert "A LAMP" in team_kpi_text and "R LAMP" in team_kpi_text

                team_update.message.reply_text.reset_mock()
                assert await teams_handler.show_team_balances(team_update, context) == TEAM_MENU_STATE
                balance_text = team_update.message.reply_text.await_args.args[0]
                assert "Остаток MINTS" in balance_text
                assert "GT:" not in balance_text
                assert "ID:" not in balance_text

        print("role simulation tests passed")
    finally:
        teams_handler.get_user_group = original_team_group
        teams_handler.load_json = original_team_load
        kpi_handler.get_user_group = original_kpi_group
        kpi_handler.load_json = original_kpi_load


if __name__ == "__main__":
    asyncio.run(main())
