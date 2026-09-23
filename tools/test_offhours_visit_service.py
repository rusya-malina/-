"""Regression tests for off-hours visit booking rules."""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import application.offhours_visit_service as visit_module
from application.offhours_visit_service import OffhoursVisitService, month_visit_dates
from repositories.json_repository import JsonRepository


def next_allowed_day(offset: int = 0) -> date:
    current = date(2026, 9, 1) + timedelta(days=offset)
    while current.weekday() not in {3, 4, 5, 6}:
        current += timedelta(days=1)
    return current


async def main() -> None:
    original_today = visit_module.local_today
    visit_module.local_today = lambda: date(2026, 9, 1)
    assert [day.day for day in month_visit_dates(date(2026, 9, 1))] == [
        3,
        4,
        5,
        6,
        10,
        11,
        12,
        13,
        17,
        18,
        19,
        20,
        24,
        25,
        26,
        27,
    ]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "offhours_visits.json"
            service = OffhoursVisitService(JsonRepository(str(path)))
            first_day = next_allowed_day()
            second_day = next_allowed_day(1)
            if second_day == first_day:
                second_day = first_day + timedelta(days=1)

            first = await service.book("101", "Алина A", "A LAMP", "bla_bla_bar", first_day.isoformat())
            assert first.ok and first.details["occupied"] == 1

            conflict = await service.book("101", "Алина A", "A LAMP", "kuranty", first_day.isoformat())
            assert not conflict.ok and conflict.code == "user_day_conflict"
            assert conflict.details["venue"] == "bla_bla_bar"

            cross_team = await service.book("202", "Рита R", "R LAMP", "bla_bla_bar", first_day.isoformat())
            assert cross_team.ok and cross_team.details["occupied"] == 2

            full = await service.book("303", "Анна A", "A LAMP", "bla_bla_bar", first_day.isoformat())
            assert not full.ok and full.code == "venue_full"

            another_day = await service.book("101", "Алина A", "A LAMP", "kuranty", second_day.isoformat())
            assert another_day.ok

            forbidden = await service.cancel("999", first.changed_ids[0])
            assert not forbidden.ok and forbidden.code == "forbidden"

            cancelled = await service.cancel("101", first.changed_ids[0])
            assert cancelled.ok
            replacement = await service.book("303", "Анна A", "A LAMP", "bla_bla_bar", first_day.isoformat())
            assert replacement.ok and replacement.details["occupied"] == 2

            user_bookings = await service.user_bookings("101")
            assert len(user_bookings) == 1
            assert user_bookings[0]["venue"] == "kuranty"

            monthly_bla_bla_day = first_day + timedelta(days=7)
            monthly_bla_bla = await service.book(
                "101", "Алина A", "A LAMP", "bla_bla_bar", monthly_bla_bla_day.isoformat()
            )
            assert monthly_bla_bla.ok
            monthly_bla_bla_second = await service.book(
                "101", "Алина A", "A LAMP", "bla_bla_bar", (first_day + timedelta(days=14)).isoformat()
            )
            assert monthly_bla_bla_second.ok
            monthly_bla_bla_limit = await service.book(
                "101", "Алина A", "A LAMP", "bla_bla_bar", (first_day + timedelta(days=21)).isoformat()
            )
            assert not monthly_bla_bla_limit.ok and monthly_bla_bla_limit.code == "user_venue_month_full"

            monthly_kuranty_second = await service.book(
                "101", "Алина A", "A LAMP", "kuranty", (second_day + timedelta(days=7)).isoformat()
            )
            assert monthly_kuranty_second.ok
            monthly_kuranty_limit = await service.book(
                "101", "Алина A", "A LAMP", "kuranty", (second_day + timedelta(days=14)).isoformat()
            )
            assert not monthly_kuranty_limit.ok and monthly_kuranty_limit.code == "user_venue_month_full"

            capacity_day = first_day + timedelta(days=7)
            capacity_results = await asyncio.gather(
                *(
                    service.book(
                        str(400 + index),
                        f"Сотрудник {index}",
                        "A LAMP",
                        "kuranty",
                        capacity_day.isoformat(),
                    )
                    for index in range(5)
                )
            )
            assert sum(result.ok for result in capacity_results) == 2
            assert sum(result.code == "venue_full" for result in capacity_results) == 3

            conflict_day = first_day + timedelta(days=14)
            conflict_results = await asyncio.gather(
                service.book("777", "Общий сотрудник", "R LAMP", "bla_bla_bar", conflict_day.isoformat()),
                service.book("777", "Общий сотрудник", "R LAMP", "kuranty", conflict_day.isoformat()),
            )
            assert sum(result.ok for result in conflict_results) == 1
            assert sum(result.code == "user_day_conflict" for result in conflict_results) == 1

            past = await service.book("909", "Прошлая дата", "A LAMP", "bla_bla_bar", "2026-08-30")
            assert not past.ok and past.code == "invalid_input"
            next_month = await service.book("910", "Следующий месяц", "A LAMP", "bla_bla_bar", "2026-10-01")
            assert not next_month.ok and next_month.code == "invalid_input"

            stored = json.loads(path.read_text(encoding="utf-8"))
            assert stored["schema_version"] == 1
            assert len(stored["history"]) == 11
            assert stored["bookings"][first.changed_ids[0]]["status"] == "cancelled"
    finally:
        visit_module.local_today = original_today


if __name__ == "__main__":
    asyncio.run(main())
    print("OFFHOURS_VISIT_SERVICE PASS")
