from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from test_role_simulation import GROUPS, ISSUANCE, KPI, USERS

import handlers.kpi as kpi_handler
import handlers.teams as teams_handler
from bot_context import TEAM_MENU_STATE


def update_for(user_id: int):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )


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
        for user_id, group in [(105, "SPV"), (106, "MNG")]:
            print(f"\\n=== ROLE SIMULATION: {group} (user_id={user_id}) ===")
            teams_handler.get_user_group = AsyncMock(return_value=group)
            kpi_handler.get_user_group = AsyncMock(return_value=group)
            context = SimpleNamespace(user_data={"admin_mode": False})

            kpi_update = update_for(user_id)
            await kpi_handler.my_kpi_menu(kpi_update, context)
            markup = kpi_update.message.reply_text.await_args.kwargs["reply_markup"]
            labels = [button.text for row in markup.inline_keyboard for button in row]
            print(f"[1] Message: {kpi_update.message.reply_text.await_args.args[0]}")
            print(f"[2] Personal KPI buttons: {labels}")

            query = SimpleNamespace(
                data="my_kpi_show_kpi",
                from_user=SimpleNamespace(id=user_id),
                answer=AsyncMock(),
                message=SimpleNamespace(edit_text=AsyncMock()),
            )
            await kpi_handler.my_kpi_callback(SimpleNamespace(callback_query=query), context)
            print("[3] Personal KPI output:")
            print(query.message.edit_text.await_args.args[0])

            team_update = update_for(user_id)
            state = await teams_handler.open_my_team_menu(team_update, context)
            print(f"[4] Open team submenu state: {state} (expected {TEAM_MENU_STATE})")
            print(f"[5] Team submenu message: {team_update.message.reply_text.await_args.args[0]}")

            team_update.message.reply_text.reset_mock()
            state = await teams_handler.show_team_kpi(team_update, context)
            print(f"[6] KPI report state: {state}")
            print("[7] KPI team report:")
            print(team_update.message.reply_text.await_args.args[0])

            team_update.message.reply_text.reset_mock()
            state = await teams_handler.show_team_balances(team_update, context)
            print(f"[8] Balance report state: {state}")
            print("[9] Balance team report:")
            print(team_update.message.reply_text.await_args.args[0])
            print(f"[10] Assertions: state_ok={state == TEAM_MENU_STATE}; ids_hidden={'ID:' not in team_update.message.reply_text.await_args.args[0]}")

        print("\\n=== TRACE RESULT: PASS ===")
    finally:
        teams_handler.get_user_group = original_team_group
        teams_handler.load_json = original_team_load
        kpi_handler.get_user_group = original_kpi_group
        kpi_handler.load_json = original_kpi_load


if __name__ == "__main__":
    asyncio.run(main())
