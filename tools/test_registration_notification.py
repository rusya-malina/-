from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handlers.user as user_handler
from bot_context import ADMIN_ID, ConversationHandler


async def test_new_registration_notifies_admin_with_actions() -> None:
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=100),
        message=SimpleNamespace(text="Петров", reply_text=AsyncMock()),
    )
    context = SimpleNamespace(
        user_data={"reg_first_name": "Иван", "reg_group": "R LAMP"},
        bot=SimpleNamespace(send_message=AsyncMock()),
    )
    saved = {}

    def save_request(mutator):
        data = {}
        result = mutator(data)
        saved.update(data)
        return result

    with patch.object(user_handler, "update_pending", new=AsyncMock(side_effect=save_request)):
        result = await user_handler.reg_get_last_name(update, context)

    assert result == ConversationHandler.END
    assert saved["100"]["name"] == "Иван Петров"
    context.bot.send_message.assert_awaited_once()
    call = context.bot.send_message.await_args.kwargs
    assert call["chat_id"] == ADMIN_ID
    assert "Новая заявка на регистрацию" in call["text"]
    assert "Иван Петров" in call["text"]
    assert "R LAMP" in call["text"]
    buttons = call["reply_markup"].inline_keyboard
    callbacks = {button.callback_data for row in buttons for button in row}
    assert "req_accept:registration:100" in callbacks
    assert "req_reject:registration:100" in callbacks


if __name__ == "__main__":
    asyncio.run(test_new_registration_notifies_admin_with_actions())
    print("REGISTRATION_NOTIFICATION PASS")
