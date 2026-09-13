"""Regression tests for off-hours visit booking rules."""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application.offhours_visit_service import OffhoursVisitService, local_today
from repositories.json_repository import JsonRepository


def next_allowed_day(offset: int = 0):
    current = local_today() + timedelta(days=offset)
    while current.weekday() not in {3, 4, 5, 6}:
        current += timedelta(days=1)
    return current


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "offhours_visits.json"
        service = OffhoursVisitService(JsonRepository(str(path)))
        first_day = next_allowed_day()
        second_day = next_allowed_day(1)
        if second_day == first_day:
            second_day = next_allowed_day(2)

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

        capacity_day = first_day + timedelta(days=7)
        capacity_results = await asyncio.gather(
            *(
                service.book(str(400 + index), f"Сотрудник {index}", "A LAMP", "kuranty", capacity_day.isoformat())
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

        stored = json.loads(path.read_text(encoding="utf-8"))
        assert stored["schema_version"] == 1
        assert len(stored["history"]) == 8
        assert stored["bookings"][first.changed_ids[0]]["status"] == "cancelled"


if __name__ == "__main__":
    asyncio.run(main())
    print("OFFHOURS_VISIT_SERVICE PASS")
