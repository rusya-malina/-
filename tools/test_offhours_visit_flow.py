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


async def main() -> None:
    assert inline_callbacks(handler.offhours_home_markup()) == [
        "offh_venue:bla_bla_bar",
        "offh_venue:kuranty",
        "offh_my",
    ]
    assert "🏪 Внерабочие посещения" in reply_labels(get_main_keyboard(101, "A LAMP"))
    assert "🏪 Внерабочие посещения" in reply_labels(get_main_keyboard(102, "R LAMP"))
    assert "🏪 Внерабочие посещения" not in reply_labels(get_main_keyboard(103, "coor A"))

    days = handler.venue_dates_markup("bla_bla_bar", [], today=date(2026, 9, 7))
    callbacks = inline_callbacks(days)
    assert callbacks[:4] == [
        "offh_book:bla_bla_bar:2026-09-10",
        "offh_book:bla_bla_bar:2026-09-11",
        "offh_book:bla_bla_bar:2026-09-12",
        "offh_book:bla_bla_bar:2026-09-13",
    ]
    assert callbacks[-1] == "offh_home"

    occupied = [
        {"venue": "bla_bla_bar", "visit_date": "2026-09-10", "name": "Алина A"},
        {"venue": "bla_bla_bar", "visit_date": "2026-09-10", "name": "Рита R"},
    ]
    full_days = handler.venue_dates_markup("bla_bla_bar", occupied, today=date(2026, 9, 7))
    assert inline_callbacks(full_days)[0] == "offh_full:bla_bla_bar:2026-09-10"
    assert "мест нет" in inline_labels(full_days)[0]

    original_identity = handler._employee_identity
    original_service = handler.OffhoursVisitService.from_default_storage

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

    try:
        handler._employee_identity = AsyncMock(return_value=("101", "Алина A", "A LAMP"))
        handler.OffhoursVisitService.from_default_storage = classmethod(lambda cls: FakeService())
        context = SimpleNamespace(user_data={})

        my_query = FakeQuery("offh_my")
        state = await handler.offhours_visit_callback(SimpleNamespace(callback_query=my_query, effective_user=my_query.from_user), context)
        assert state == OFFHOURS_VISITS_MENU
        my_text = my_query.message.edit_text.await_args.args[0]
        assert "Bla Bla Bar" in my_text and "10.09.2026" in my_text
        assert inline_callbacks(my_query.message.edit_text.await_args.kwargs["reply_markup"]) == [
            "offh_cancel_menu",
            "offh_schedule",
            "offh_home",
        ]

        schedule_query = FakeQuery("offh_schedule")
        await handler.offhours_visit_callback(SimpleNamespace(callback_query=schedule_query, effective_user=schedule_query.from_user), context)
        schedule_text = schedule_query.message.edit_text.await_args.args[0]
        assert "Алина A" in schedule_text and "Рита R" in schedule_text
        assert "Bla Bla Bar" in schedule_text and "Куранты" in schedule_text
    finally:
        handler._employee_identity = original_identity
        handler.OffhoursVisitService.from_default_storage = original_service


if __name__ == "__main__":
    asyncio.run(main())
    print("OFFHOURS_VISIT_FLOW PASS")
