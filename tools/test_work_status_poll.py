"""Regression tests for the daily work-status poll."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from handlers import work_status


def test_poll_skips_employees_who_already_voted() -> None:
    sent: list[dict] = []

    async def fake_recipients():
        return [
            {"user_id": "101", "name": "Аня Один", "group": "A LAMP"},
            {"user_id": "102", "name": "Бэлла Два", "group": "R LAMP"},
        ]

    async def fake_status(user_id: str):
        return {"status": "working"} if user_id == "101" else {}

    class FakeBot:
        async def send_message(self, **kwargs):
            sent.append(kwargs)

    original_recipients = work_status.get_work_status_recipients
    original_status = work_status.get_today_status
    work_status.get_work_status_recipients = fake_recipients
    work_status.get_today_status = fake_status
    try:
        asyncio.run(work_status.send_work_status_poll_job(SimpleNamespace(bot=FakeBot())))
    finally:
        work_status.get_work_status_recipients = original_recipients
        work_status.get_today_status = original_status

    assert [message["chat_id"] for message in sent] == [102]
    assert sent[0]["text"] == "Вы работаете сегодня?"
    assert sent[0]["reply_markup"].inline_keyboard[0][0].callback_data == "work_status:set:working"


if __name__ == "__main__":
    test_poll_skips_employees_who_already_voted()
    print("WORK_STATUS_POLL PASS")
