"""Regression tests for the off-hours visit Telegram flow."""
from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handlers.offhours_visits as handler
from keyboards import get_main_keyboard
from states import OFFHOURS_VISITS_MENU


def inline_callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def inline_labels(markup):
    return [button.text for row in markup.inline_keyboard for button in row]


def reply_labels(markup):
    return [button.text for row in markup.keyboard for button in row]


class FakeQuery:
    def __init__(self, data: str, user_id: int = 101):
        self.data = data
        self.from_user = SimpleNamespace(id=user_id, full_name="Алина A")
        self.message = SimpleNamespace(edit_text=AsyncMock())
        self.answer = AsyncMock()


class FakeService:
    async def active_bookings(self):
        return [
            {
                "booking_id": "one",
                "user_id": "101",
                "name": "Алина A",
                "group": "A LAMP",
                "venue": "bla_bla_bar",
                "visit_date": "2026-09-10",
                "status": "active",
            },
            {
                "booking_id": "two",
                "user_id": "202",
                "name": "Рита R",
                "group": "R LAMP",
                "venue": "bla_bla_bar",
                "visit_date": "2026-09-10",
                "status": "active",
            },
        ]

    async def user_bookings(self, user_id):
        return [item for item in await self.active_bookings() if item["user_id"] == str(user_id)]


async def main() -> None:
    assert inline_callbacks(handler.offhours_home_markup()) == [
        "offh_venue:bla_bla_bar",
        "offh_venue:kuranty",
        "offh_my",
    ]
    assert "🏪 Внерабочие посещения" in reply_labels(get_main_keyboard(101, "A LAMP"))
    assert "🏪 Внерабочие посещения" in reply_labels(get_main_keyboard(102, "R LAMP"))
    assert "🏪 Внерабочие посещения" not in reply_labels(get_main_keyboard(103, "coor A"))
    assert "Брони" in reply_labels(get_main_keyboard(103, "coor A"))
    assert "Брони" in reply_labels(get_main_keyboard(104, "coor R"))
    assert "Брони" in reply_labels(get_main_keyboard(105, "SPV"))
    assert "Брони" in reply_labels(get_main_keyboard(106, "MNG"))
    assert "Брони" not in reply_labels(get_main_keyboard(101, "A LAMP"))

    month_markup = handler.venue_dates_markup("bla_bla_bar", [], today=date(2026, 9, 7))
    callbacks = inline_callbacks(month_markup)
    expected_days = [3, 4, 5, 6, 10, 11, 12, 13, 17, 18, 19, 20, 24, 25, 26, 27]
    assert callbacks[:-1] == [f"offh_day:bla_bla_bar:2026-09-{day:02d}" for day in expected_days]
    assert callbacks[-1] == "offh_home"
    assert all(len(row) == 4 for row in month_markup.inline_keyboard[:-1])
    assert inline_labels(month_markup)[0] == "Ч 03·"

    occupied = [
        {"venue": "bla_bla_bar", "visit_date": "2026-09-10", "name": "Алина A"},
        {"venue": "bla_bla_bar", "visit_date": "2026-09-10", "name": "Рита R"},
    ]
    full_month = handler.venue_dates_markup("bla_bla_bar", occupied, today=date(2026, 9, 7))
    assert "Ч 10✖" in inline_labels(full_month)

    original_identity = handler._employee_identity
    original_service = handler.OffhoursVisitService.from_default_storage
    original_today = handler.local_today
    original_group = handler.get_user_group
    try:
        handler._employee_identity = AsyncMock(return_value=("101", "Алина A", "A LAMP"))
        handler.OffhoursVisitService.from_default_storage = classmethod(lambda cls: FakeService())
        handler.local_today = lambda: date(2026, 9, 7)
        context = SimpleNamespace(user_data={})

        day_query = FakeQuery("offh_day:bla_bla_bar:2026-09-10")
        state = await handler.offhours_visit_callback(
            SimpleNamespace(callback_query=day_query, effective_user=day_query.from_user), context
        )
        assert state == OFFHOURS_VISITS_MENU
        day_text = day_query.message.edit_text.await_args.args[0]
        assert "Алина A" in day_text and "Рита R" in day_text and "Все два места заняты" in day_text
        assert inline_callbacks(day_query.message.edit_text.await_args.kwargs["reply_markup"]) == [
            "offh_venue:bla_bla_bar"
        ]

        free_query = FakeQuery("offh_day:kuranty:2026-09-11")
        await handler.offhours_visit_callback(
            SimpleNamespace(callback_query=free_query, effective_user=free_query.from_user), context
        )
        free_text = free_query.message.edit_text.await_args.args[0]
        assert "Броней нет" in free_text and "Свободно мест: 2 из 2" in free_text
        assert inline_callbacks(free_query.message.edit_text.await_args.kwargs["reply_markup"]) == [
            "offh_confirm:kuranty:2026-09-11",
            "offh_venue:kuranty",
        ]

        past_query = FakeQuery("offh_day:kuranty:2026-09-04")
        await handler.offhours_visit_callback(
            SimpleNamespace(callback_query=past_query, effective_user=past_query.from_user), context
        )
        past_text = past_query.message.edit_text.await_args.args[0]
        assert "дата уже прошла" in past_text
        assert "offh_confirm:kuranty:2026-09-04" not in inline_callbacks(
            past_query.message.edit_text.await_args.kwargs["reply_markup"]
        )

        my_query = FakeQuery("offh_my")
        state = await handler.offhours_visit_callback(
            SimpleNamespace(callback_query=my_query, effective_user=my_query.from_user), context
        )
        assert state == OFFHOURS_VISITS_MENU
        my_text = my_query.message.edit_text.await_args.args[0]
        assert "Bla Bla Bar" in my_text and "10.09.2026" in my_text
        assert inline_callbacks(my_query.message.edit_text.await_args.kwargs["reply_markup"]) == [
            "offh_cancel_menu",
            "offh_schedule",
            "offh_home",
        ]

        schedule_query = FakeQuery("offh_schedule")
        await handler.offhours_visit_callback(
            SimpleNamespace(callback_query=schedule_query, effective_user=schedule_query.from_user), context
        )
        schedule_text = schedule_query.message.edit_text.await_args.args[0]
        assert "Алина A" in schedule_text and "Рита R" in schedule_text
        assert "Bla Bla Bar" in schedule_text and "Куранты" in schedule_text
        assert "Расписание за 09.2026" in schedule_text

        handler.get_user_group = AsyncMock(return_value="SPV")
        coordinator_message = SimpleNamespace(reply_text=AsyncMock())
        coordinator_update = SimpleNamespace(
            effective_user=SimpleNamespace(id=303),
            message=coordinator_message,
        )
        await handler.show_coordinator_bookings(coordinator_update, context)
        report = coordinator_message.reply_text.await_args.args[0]
        assert "Брони за 09.2026" in report
        assert "Ч 10.09 — Алина A + Рита R" in report
        assert "Куранты" in report and "—" in report

        handler.get_user_group = AsyncMock(return_value="MNG")
        manager_message = SimpleNamespace(reply_text=AsyncMock())
        manager_update = SimpleNamespace(effective_user=SimpleNamespace(id=404), message=manager_message)
        await handler.show_coordinator_bookings(manager_update, context)
        manager_report = manager_message.reply_text.await_args.args[0]
        assert "Брони за 09.2026" in manager_report and "Алина A + Рита R" in manager_report
    finally:
        handler._employee_identity = original_identity
        handler.OffhoursVisitService.from_default_storage = original_service
        handler.local_today = original_today
        handler.get_user_group = original_group


if __name__ == "__main__":
    asyncio.run(main())
    print("OFFHOURS_VISIT_FLOW PASS")
