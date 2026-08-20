import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handlers.kpi as kpi_handler
import handlers.teams as teams_handler
from bot_context import TEAM_MENU_STATE
from organization import (
    build_employee_registry,
    get_visible_users,
    merge_employee_issuance,
)

USERS = {
    "10": "Алиса Смирнова",
    "excel_алиса_смирнова": "Алиса Смирнова",
    "99": "Координатор A",
}
GROUPS = {
    "10": {"group": "A LAMP"},
    "excel_алиса_смирнова": {"group": "A LAMP"},
    "99": {"group": "coor A"},
}
KPI = {
    "алиса смирнова": {
        "original_name": "Алиса Смирнова",
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
}
ISSUANCE = {
    "10": {"name": "Алиса Смирнова", "mints_issued": 10, "sticks_issued": 8, "history": []},
    "excel_алиса_смирнова": {"name": "Алиса Смирнова", "mints_issued": 5, "sticks_issued": 2, "history": []},
}


def update_for(user_id: int):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )


async def main() -> None:
    registry = build_employee_registry(USERS, GROUPS, KPI, ISSUANCE)
    alice = next(item for item in registry if item["name"] == "Алиса Смирнова")
    assert len(registry) == 2
    assert alice["user_id"] == "10"
    assert alice["aliases"] == ["10", "excel_алиса_смирнова"]
    assert merge_employee_issuance(alice, ISSUANCE)["mints_issued"] == 15
    assert merge_employee_issuance(alice, ISSUANCE)["sticks_issued"] == 10

    visible = get_visible_users(99, USERS, GROUPS, exclude_user_id=99, kpi_data=KPI, issuance_data=ISSUANCE)
    assert [item["name"] for item in visible] == ["Алиса Смирнова"]
    assert visible[0]["user_id"] == "10"

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
        if path == kpi_handler.GROUPS_FILE:
            return GROUPS
        if path == kpi_handler.KPI_FILE:
            return KPI
        if path == kpi_handler.ISSUANCE_FILE:
            return ISSUANCE
        return {}

    try:
        teams_handler.get_user_group = AsyncMock(return_value="coor A")
        teams_handler.load_json = team_load
        kpi_handler.get_user_group = AsyncMock(return_value="A LAMP")
        kpi_handler.load_json = kpi_load
        context = SimpleNamespace(user_data={})

        personal_kpi_query = SimpleNamespace(
            data="my_kpi_show_kpi",
            from_user=SimpleNamespace(id=10),
            answer=AsyncMock(),
            message=SimpleNamespace(edit_text=AsyncMock()),
        )
        await kpi_handler.my_kpi_callback(SimpleNamespace(callback_query=personal_kpi_query), context)
        personal_kpi_text = personal_kpi_query.message.edit_text.await_args.args[0]
        assert "Алиса Смирнова" in personal_kpi_text
        assert "75.0%" in personal_kpi_text

        balance_update = update_for(10)
        await kpi_handler.show_balances(balance_update, context)
        balance_text = balance_update.message.reply_text.await_args.args[0]
        assert "Выдано: `15`" in balance_text
        assert "Выдано: `10`" in balance_text

        team_update = update_for(99)
        assert await teams_handler.show_team_kpi(team_update, context) == TEAM_MENU_STATE
        team_kpi_text = team_update.message.reply_text.await_args.args[0]
        assert "Сотрудников в командах: **1**" in team_kpi_text
        assert team_kpi_text.count("Алиса Смирнова") == 1

        team_update.message.reply_text.reset_mock()
        assert await teams_handler.show_team_balances(team_update, context) == TEAM_MENU_STATE
        team_balance_text = team_update.message.reply_text.await_args.args[0]
        assert "Сотрудников в командах: **1**" in team_balance_text
        assert "Остаток MINTS: -55" in team_balance_text
        assert "стиков: -70" in team_balance_text
        print("UNIFIED_EMPLOYEE_REPORTS PASS")
    finally:
        teams_handler.get_user_group = original_team_group
        teams_handler.load_json = original_team_load
        kpi_handler.get_user_group = original_kpi_group
        kpi_handler.load_json = original_kpi_load


if __name__ == "__main__":
    asyncio.run(main())
