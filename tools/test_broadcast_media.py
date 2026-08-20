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
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)
        return FakeStatus()


class FakeBot:
    def __init__(self):
        self.calls = []

    async def send_message(self, **kwargs):
        self.calls.append(("message", kwargs))

    async def send_photo(self, **kwargs):
        self.calls.append(("photo", kwargs))

    async def send_document(self, **kwargs):
        self.calls.append(("document", kwargs))


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
    result, calls = await run_case(FakeMessage(text="Тестовый текст"))
    assert result == broadcast.ConversationHandler.END
    assert [kind for kind, _ in calls] == ["message", "message"]
    assert all(call[1]["text"] == "Тестовый текст" for call in calls)

    result, calls = await run_case(
        FakeMessage(
            caption="Подпись к фото",
            photo=[SimpleNamespace(file_id="photo-1")],
        )
    )
    assert result == broadcast.ConversationHandler.END
    assert [kind for kind, _ in calls] == ["photo", "photo"]
    assert all(call[1]["photo"] == "photo-1" for call in calls)

    result, calls = await run_case(
        FakeMessage(
            caption="Файл KPI",
            document=SimpleNamespace(file_id="document-1"),
        )
    )
    assert result == broadcast.ConversationHandler.END
    assert [kind for kind, _ in calls] == ["document", "document"]
    assert all(call[1]["document"] == "document-1" for call in calls)

    print("broadcast text/photo/document tests passed")


if __name__ == "__main__":
    asyncio.run(main())
