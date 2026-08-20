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
    assert projection["hours_left"] == 28
    target_100, target_111 = projection["rows"]
    assert target_100["target_percent"] == 100
    assert target_100["gt_remaining"] == 4
    assert target_100["micro_remaining"] == 41
    assert target_100["gt_per_hour_rounded"] == 1
    assert target_100["micro_per_hour_rounded"] == 2
    assert target_111["target_percent"] == 111
    assert round(target_111["gt_remaining"], 1) == 13.9
    assert round(target_111["micro_remaining"], 2) == 55.08
    assert target_111["gt_per_hour_rounded"] == 1
    assert target_111["micro_per_hour_rounded"] == 2

    assert "📅 План" in button_texts(get_main_keyboard(101, group="A LAMP"))
    assert "📅 План" in button_texts(get_main_keyboard(102, group="R LAMP"))
    assert "📅 План" not in button_texts(get_main_keyboard(103, group="coor A"))
    assert "📅 План" not in button_texts(get_main_keyboard(104, group="SPV"))

    async def handler_case(group: str) -> str:
        original_load = kpi_handler.load_json
        original_group = kpi_handler.get_user_group
        users = {"101": {"name": "A One"}}
        groups = {"101": {"name": "A One", "group": group}}
        kpi = {
            "a one": {
                "original_name": "A One",
                "gt_plan": 90,
                "gt_fact": 86,
                "micro_plan": 128,
                "micro_las_fact": 47,
                "micro_lau_fact": 40,
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
        assert "Осталось рабочих дней" in text
        assert "Цель 100%" in text and "Цель 111%" in text
        assert "Общие микроакты" in text and "в час" in text
        denied = await handler_case("coor A")
        assert "доступен только сотрудникам A LAMP и R LAMP" in denied

    asyncio.run(handler_tests())
    print("PLAN_PROJECTION PASS")


if __name__ == "__main__":
    main()
