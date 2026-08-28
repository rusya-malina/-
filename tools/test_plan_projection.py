"""Contract tests for the user-facing hourly KPI plan."""
from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handlers.kpi as kpi_handler
from application.kpi_service import build_plan_projection, remaining_workdays
from keyboards import get_main_keyboard


def button_texts(markup) -> list[str]:
    return [button.text for row in markup.keyboard for button in row]


def main() -> None:
    as_of = date(2026, 8, 21)
    assert remaining_workdays(as_of, date(2026, 8, 31)) == 7
    projection = build_plan_projection(
        {
            "gt_plan": 90,
            "gt_fact": 86,
            "micro_plan": 128,
            "micro_las_fact": 47,
            "micro_lau_fact": 40,
        },
        as_of=as_of,
    )
    assert projection["workdays_left"] == 7
    target_100, target_111 = projection["rows"]
    assert target_100["target_percent"] == 100
    assert target_100["gt_remaining"] == 4
    assert target_100["las_remaining"] == 5
    assert target_100["lau_remaining"] == 37
    assert target_100["micro_total_remaining"] == 42
    assert target_100["gt_per_hour_rounded"] == 1
    assert target_100["las_per_hour_rounded"] == 2
    assert target_100["lau_per_hour_rounded"] == 2
    assert round(projection["current_threshold_percent"], 2) == 54.02
    assert target_100["las_per_hour_rounded"] / (target_100["las_per_hour_rounded"] + target_100["lau_per_hour_rounded"]) > 0.40
    assert target_111["target_percent"] == 111
    assert round(target_111["gt_remaining"], 1) == 13.9
    assert target_111["las_remaining"] == 11
    assert target_111["lau_remaining"] == 46
    assert target_111["micro_total_remaining"] == 57
    assert target_111["gt_per_hour_rounded"] == 1
    assert target_111["las_per_hour_rounded"] == 2
    assert target_111["lau_per_hour_rounded"] == 2
    assert target_111["las_per_hour_rounded"] / (target_111["las_per_hour_rounded"] + target_111["lau_per_hour_rounded"]) > 0.40

    production_case = build_plan_projection(
        {
            "gt_plan": 90,
            "gt_fact": 70,
            "micro_plan": 128,
            "micro_las_fact": 51,
            "micro_lau_fact": 66,
        },
        as_of=date(2026, 8, 26),
    )
    assert production_case["workdays_left"] == 4
    assert production_case["hours_left"] == 16
    assert round(production_case["current_threshold_percent"], 2) == 43.59
    production_100, production_111 = production_case["rows"]
    assert production_100["gt_remaining"] == 20
    assert production_100["gt_per_hour"] == 1.25
    assert production_100["gt_per_hour_rounded"] == 2
    assert production_111["gt_remaining"] == 29.900000000000006
    assert production_111["gt_per_hour_rounded"] == 2
    for row in (production_100, production_111):
        rounded_total = row["las_per_hour_rounded"] + row["lau_per_hour_rounded"]
        assert row["las_per_hour_rounded"] / rounded_total > 0.40

    lau_overachieved = build_plan_projection(
        {
            "gt_plan": 90,
            "gt_fact": 70,
            "micro_plan": 128,
            "micro_las_fact": 51,
            "micro_lau_fact": 150,
        },
        as_of=date(2026, 8, 26),
    )
    for row in lau_overachieved["rows"]:
        assert row["las_target"] >= 101
        assert row["las_remaining"] == 50
        assert row["lau_remaining"] == 0
        assert row["use_las_only"] is True

    assert "📅 План" in button_texts(get_main_keyboard(101, group="A LAMP"))
    assert "📅 План" in button_texts(get_main_keyboard(102, group="R LAMP"))
    assert "📅 План" not in button_texts(get_main_keyboard(103, group="coor A"))
    assert "📅 План" not in button_texts(get_main_keyboard(104, group="SPV"))

    async def handler_case(group: str, gt_fact: int = 86, micro_las_fact: int = 47, micro_lau_fact: int = 40) -> str:
        original_load = kpi_handler.load_json
        original_group = kpi_handler.get_user_group
        users = {"101": {"name": "A One"}}
        groups = {"101": {"name": "A One", "group": group}}
        kpi = {
            "a one": {
                "original_name": "A One",
                "gt_plan": 90,
                "gt_fact": gt_fact,
                "micro_plan": 128,
                "micro_las_fact": micro_las_fact,
                "micro_lau_fact": micro_lau_fact,
            }
        }
        issuance = {"_schema_version": 2}

        async def load(path):
            return {
                kpi_handler.USERS_FILE: users,
                kpi_handler.GROUPS_FILE: groups,
                kpi_handler.KPI_FILE: kpi,
                kpi_handler.ISSUANCE_FILE: issuance,
            }.get(path, {})

        try:
            kpi_handler.load_json = load
            kpi_handler.get_user_group = AsyncMock(return_value=group)
            message = SimpleNamespace(reply_text=AsyncMock())
            update = SimpleNamespace(effective_user=SimpleNamespace(id=101), message=message)
            await kpi_handler.show_plan(update, SimpleNamespace(user_data={}))
            return message.reply_text.await_args.args[0]
        finally:
            kpi_handler.load_json = original_load
            kpi_handler.get_user_group = original_group

    async def handler_tests() -> None:
        text = await handler_case("A LAMP")
        assert "Персональная карточка плана" in text
        assert "На дату:" in text and "Осталось рабочих дней" in text
        assert "GT" in text and "100%" in text and "111%" in text
        assert "Микроакты LAS / LAU" in text
        assert "LAS:" in text and "LAU:" in text
        assert "40% threshold" not in text
        assert "Текущий threshold LAS: `54.02%` — **соблюдён** (норма > 40%)" in text
        assert "100% план —" in text and "111% план —" in text
        assert "(Итого LAS: `5`, LAU: `37`)" in text
        assert "(Итого LAS: `11`, LAU: `46`)" in text
        assert "Общие микроакты" not in text
        assert "Статус" in text and "Общий статус" in text
        overachieved = await handler_case("A LAMP", gt_fact=120, micro_las_fact=80, micro_lau_fact=80)
        assert overachieved.count("План перевыполнен") == 8
        las_only = await handler_case("A LAMP", gt_fact=70, micro_las_fact=60, micro_lau_fact=100)
        assert "Текущий threshold LAS: `37.50%` — **ниже нормы** (норма > 40%)" in las_only
        assert las_only.count("LAU: `0/час`") == 2
        assert las_only.count("Итого LAS: `7`, LAU: `0`") == 2
        denied = await handler_case("coor A")
        assert "доступен только сотрудникам A LAMP и R LAMP" in denied

    asyncio.run(handler_tests())
    print("PLAN_PROJECTION PASS")


if __name__ == "__main__":
    main()
