"""Regression tests for the daily work-status poll."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

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


def test_status_answer_returns_to_main_menu() -> None:
    query = SimpleNamespace(
        from_user=SimpleNamespace(id=101),
        data="work_status:set:working",
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock(), reply_text=AsyncMock()),
    )
    original_group = work_status.get_user_group
    original_set_status = work_status.set_work_status
    work_status.get_user_group = AsyncMock(return_value="A LAMP")
    work_status.set_work_status = AsyncMock(return_value={"ok": True})
    try:
        asyncio.run(work_status.work_status_callback(SimpleNamespace(callback_query=query), SimpleNamespace()))
    finally:
        work_status.get_user_group = original_group
        work_status.set_work_status = original_set_status

    query.message.reply_text.assert_awaited_once()
    menu_markup = query.message.reply_text.await_args.kwargs["reply_markup"]
    menu_labels = [button.text for row in menu_markup.keyboard for button in row]
    assert "📅 План" in menu_labels
    assert "Мой KPI" in menu_labels


if __name__ == "__main__":
    test_poll_skips_employees_who_already_voted()
    test_status_answer_returns_to_main_menu()
    print("WORK_STATUS_POLL PASS")
