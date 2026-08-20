from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handlers.broadcast as broadcast


class FakeStatus:
    def __init__(self):
        self.edited = None

    async def edit_text(self, text, **kwargs):
        self.edited = text


class FakeMessage:
    def __init__(self, *, text=None, caption=None, photo=None, document=None):
        self.text = text
        self.caption = caption
        self.photo = photo
        self.document = document
        self.chat_id = 14599689
        self.message_id = 777
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        return FakeStatus()


class FakeBot:
    def __init__(self):
        self.calls = []

    async def copy_message(self, **kwargs):
        self.calls.append(("copy", kwargs))


async def run_case(message):
    users = {"101": "A User", "102": "B User", "excel_fake": "Ignored"}
    original_load_json = broadcast.load_json
    broadcast.load_json = lambda _path: asyncio.sleep(0, result=users)
    try:
        bot = FakeBot()
        update = SimpleNamespace(
            message=message,
            effective_user=SimpleNamespace(id=14599689),
        )
        context = SimpleNamespace(bot=bot)
        result = await broadcast.send_broadcast(update, context)
        return result, bot.calls
    finally:
        broadcast.load_json = original_load_json


async def main():
    for message in (
        FakeMessage(text="Тестовый текст"),
        FakeMessage(
            caption="Подпись к фото",
            photo=[SimpleNamespace(file_id="photo-1")],
        ),
        FakeMessage(
            caption="Файл KPI",
            document=SimpleNamespace(file_id="document-1", file_name="presentation.pptx"),
        ),
    ):
        result, calls = await run_case(message)
        assert result == broadcast.ConversationHandler.END
        assert [kind for kind, _ in calls] == ["copy", "copy"]
        assert all(call[1]["from_chat_id"] == 14599689 for call in calls)
        assert all(call[1]["message_id"] == 777 for call in calls)
        assert all(call[1]["chat_id"] in (101, 102) for call in calls)

    print("broadcast copyMessage text/photo/document tests passed")


if __name__ == "__main__":
    asyncio.run(main())
