from __future__ import annotations

import asyncio
from types import SimpleNamespace

from application.group_report_service import refresh_existing_group_reports


class FakeBot:
    def __init__(self) -> None:
        self.deleted: list[dict] = []
        self.sent: list[dict] = []
        self._next_id = 300

    async def delete_message(self, **kwargs):
        self.deleted.append(kwargs)

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        self._next_id += 1
        return SimpleNamespace(message_id=self._next_id)


async def scenario() -> None:
    bot = FakeBot()
    context = SimpleNamespace(
        bot=bot,
        bot_data={
            "group_report_message_ids": {
                "-100:work_status": 101,
                "-100:bookings": 202,
            }
        },
    )

    refreshed = await refresh_existing_group_reports(
        context,
        report_type="work_status",
        text="актуальный статус",
    )

    assert refreshed == 1
    assert bot.deleted == [{"chat_id": -100, "message_id": 101}]
    assert bot.sent[0]["chat_id"] == -100
    assert bot.sent[0]["text"] == "актуальный статус"
    assert context.bot_data["group_report_message_ids"]["-100:bookings"] == 202


def main() -> None:
    asyncio.run(scenario())
    print("GROUP_REPORT_ISOLATION PASS")


if __name__ == "__main__":
    main()
