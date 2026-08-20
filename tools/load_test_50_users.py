from __future__ import annotations

import asyncio
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handlers.kpi as kpi_handler
import handlers.teams as teams_handler
from bot_context import ADMIN_ID, TEAM_MENU_STATE
from keyboards import get_main_keyboard

ROLE_COUNTS = {
    "A LAMP": 15,
    "R LAMP": 15,
    "coor A": 5,
    "coor R": 5,
    "SPV": 5,
    "MNG": 4,
}
MANAGER_ROLES = {"coor A", "coor R", "SPV", "MNG"}


def build_fixture() -> tuple[dict, dict, dict, dict, dict]:
    users = {}
    groups = {}
    kpi = {}
    issuance = {}
    role_by_id = {}
    next_id = 500000000

    for role, count in ROLE_COUNTS.items():
        for index in range(count):
            user_id = str(next_id)
            next_id += 1
            name = f"Load {role} {index + 1}"
            users[user_id] = name
            groups[user_id] = {"group": role}
            role_by_id[user_id] = role
            kpi[name.lower()] = {
                "original_name": name,
                "gt_plan": 100,
                "gt_fact": 85,
                "micro_plan": 100,
                "micro_las_fact": 45,
                "micro_lau_fact": 35,
                "retrafic_plan": 100,
                "retrafic_fact": 80,
                "office_hours": 10,
                "field_hours": 5,
            }
            issuance[user_id] = {
                "name": name,
                "mints_issued": 10,
                "sticks_issued": 10,
                "history": [],
            }

    admin_id = str(ADMIN_ID)
    users[admin_id] = "Load Admin"
    groups[admin_id] = {"group": "coor R"}
    role_by_id[admin_id] = "coor R"
    kpi["load admin"] = {
        "original_name": "Load Admin",
        "gt_plan": 100,
        "gt_fact": 90,
        "micro_plan": 100,
        "micro_las_fact": 50,
        "micro_lau_fact": 40,
        "retrafic_plan": 100,
        "retrafic_fact": 90,
        "office_hours": 10,
        "field_hours": 5,
    }
    issuance[admin_id] = {"name": "Load Admin", "mints_issued": 10, "sticks_issued": 10, "history": []}
    role_by_id[admin_id] = "coor R"
    return users, groups, kpi, issuance, role_by_id


def message_update(user_id: int):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        message=SimpleNamespace(reply_text=AsyncMock()),
    )


async def main() -> None:
    users, groups, kpi, issuance, role_by_id = build_fixture()
    before = json.dumps({"users": users, "groups": groups, "kpi": kpi, "issuance": issuance}, ensure_ascii=False, sort_keys=True)
    original_team_group = teams_handler.get_user_group
    original_team_load = teams_handler.load_json
    original_kpi_group = kpi_handler.get_user_group
    original_kpi_load = kpi_handler.load_json

    async def team_group(user_id):
        return role_by_id[str(user_id)]

    async def kpi_group(user_id):
        return role_by_id[str(user_id)]

    async def team_load(path):
        if path == teams_handler.USERS_FILE:
            return users
        if path == teams_handler.GROUPS_FILE:
            return groups
        if path == teams_handler.KPI_FILE:
            return kpi
        if path == teams_handler.ISSUANCE_FILE:
            return issuance
        return {}

    async def kpi_load(path):
        if path == kpi_handler.USERS_FILE:
            return users
        if path == kpi_handler.KPI_FILE:
            return kpi
        return {}

    teams_handler.get_user_group = team_group
    teams_handler.load_json = team_load
    kpi_handler.get_user_group = kpi_group
    kpi_handler.load_json = kpi_load

    scenarios: defaultdict[str, list[float]] = defaultdict(list)
    errors: list[dict] = []
    barrier = asyncio.Event()

    async def user_scenario(user_id: int):
        role = role_by_id[str(user_id)]
        admin_mode = user_id == ADMIN_ID
        context = SimpleNamespace(user_data={"admin_mode": admin_mode})
        await barrier.wait()
        try:
            started = time.perf_counter()
            menu = get_main_keyboard(user_id, admin_mode=admin_mode, group=role)
            menu_labels = {button.text for row in menu.keyboard for button in row}
            assert menu_labels
            scenarios["main_menu"].append((time.perf_counter() - started) * 1000)

            kpi_update = message_update(user_id)
            started = time.perf_counter()
            await kpi_handler.my_kpi_menu(kpi_update, context)
            query = SimpleNamespace(
                data="my_kpi_show_kpi",
                from_user=SimpleNamespace(id=user_id),
                answer=AsyncMock(),
                message=SimpleNamespace(edit_text=AsyncMock()),
            )
            await kpi_handler.my_kpi_callback(SimpleNamespace(callback_query=query), context)
            personal_text = query.message.edit_text.await_args.args[0]
            assert "Re-trafic" in personal_text and "%" in personal_text
            scenarios["personal_kpi"].append((time.perf_counter() - started) * 1000)

            if role in MANAGER_ROLES or admin_mode:
                team_update = message_update(user_id)
                started = time.perf_counter()
                state = await teams_handler.open_my_team_menu(team_update, context)
                assert state == TEAM_MENU_STATE
                scenarios["team_menu"].append((time.perf_counter() - started) * 1000)

                team_update.message.reply_text.reset_mock()
                started = time.perf_counter()
                state = await teams_handler.show_team_kpi(team_update, context)
                text = team_update.message.reply_text.await_args.args[0]
                assert state == TEAM_MENU_STATE and "Re-trafic" in text and "ID:" not in text
                scenarios["team_kpi"].append((time.perf_counter() - started) * 1000)

                team_update.message.reply_text.reset_mock()
                started = time.perf_counter()
                state = await teams_handler.show_team_balances(team_update, context)
                text = team_update.message.reply_text.await_args.args[0]
                assert state == TEAM_MENU_STATE and "Остаток MINTS" in text and "GT:" not in text
                scenarios["team_balances"].append((time.perf_counter() - started) * 1000)
        except Exception as error:  # noqa: BLE001 - harness records every scenario failure
            errors.append({"user_id": user_id, "role": role, "error": repr(error)})

    tasks = [asyncio.create_task(user_scenario(int(user_id))) for user_id in users]
    await asyncio.sleep(0)
    started_all = time.perf_counter()
    barrier.set()
    await asyncio.gather(*tasks)
    total_ms = (time.perf_counter() - started_all) * 1000

    after = json.dumps({"users": users, "groups": groups, "kpi": kpi, "issuance": issuance}, ensure_ascii=False, sort_keys=True)
    assert before == after, "fixture data changed during load test"

    print("LOAD TEST: 50 concurrent users")
    print("ROLE DISTRIBUTION:", dict(ROLE_COUNTS), "ADMIN_ID=1")
    print(f"TOTAL_USERS={len(users)} TOTAL_ELAPSED_MS={total_ms:.2f} THROUGHPUT_USERS_PER_SEC={len(users)/(total_ms/1000):.2f}")
    print(f"SUCCESS_USERS={len(users)-len(errors)} ERROR_USERS={len(errors)}")
    for scenario, values in sorted(scenarios.items()):
        ordered = sorted(values)
        p50 = statistics.median(ordered)
        p95 = ordered[min(len(ordered) - 1, max(0, int(len(ordered) * 0.95) - 1))]
        print(f"SCENARIO {scenario}: count={len(values)} p50_ms={p50:.3f} p95_ms={p95:.3f} max_ms={max(ordered):.3f}")
    print("DATA_INTEGRITY=PASS")
    if errors:
        print("ERRORS:", errors)
        raise AssertionError(f"load test had {len(errors)} errors")
    print("LOAD_TEST_RESULT=PASS")

    teams_handler.get_user_group = original_team_group
    teams_handler.load_json = original_team_load
    kpi_handler.get_user_group = original_kpi_group
    kpi_handler.load_json = original_kpi_load


if __name__ == "__main__":
    asyncio.run(main())
