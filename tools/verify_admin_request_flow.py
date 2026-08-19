from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from unittest.mock import AsyncMock

import handlers.requests as request_handlers
import handlers.teams as team_handlers
from bot_context import ADMIN_ID, ConversationHandler, GROUPS_FILE, GROUPS_WITH_BALANCES, GROUPS_WITH_HOURS, TEAM_REQUESTS_FILE, TEAMS_FILE, USERS_FILE


class FakeMessage:
    def __init__(self):
        self.chat_id = ADMIN_ID
        self.edit_text = AsyncMock()
        self.delete = AsyncMock()


class FakeQuery:
    def __init__(self, data: str):
        self.data = data
        self.from_user = SimpleNamespace(id=ADMIN_ID)
        self.message = FakeMessage()
        self.answer = AsyncMock()


class FakeBot:
    def __init__(self):
        self.send_message = AsyncMock()


class FakeContext:
    def __init__(self):
        self.bot = FakeBot()
        self.user_data = {}


async def verify_registration_accept() -> None:
    original = {
        'load_request_inbox': request_handlers.load_request_inbox,
        'update_pending': request_handlers.update_pending,
        'load_json': request_handlers.load_json,
        'save_json': request_handlers.save_json,
    }
    request_handlers.load_request_inbox = AsyncMock(return_value=[{
        'id': 'registration:100',
        'kind': 'registration',
        'user_id': '100',
        'name': 'Тест Пользователь',
        'group': 'A LAMP',
        'text': 'Выбранная группа: A LAMP.',
    }])
    request_handlers.update_pending = AsyncMock(return_value={'name': 'Тест Пользователь', 'group': 'A LAMP'})

    async def load_json(path):
        if path == request_handlers.USERS_FILE:
            return {'100': 'Тест Пользователь'}
        if path == request_handlers.GROUPS_FILE:
            return {}
        return {}

    request_handlers.load_json = load_json
    request_handlers.save_json = AsyncMock()
    try:
        query = FakeQuery('req_accept:registration:100')
        context = FakeContext()
        result = await request_handlers.requests_callback(SimpleNamespace(callback_query=query), context)
        assert result == ConversationHandler.END
        assert query.answer.await_count == 1
        keyboard = context.bot.send_message.await_args.kwargs['reply_markup']
        labels = {button.text for row in keyboard.keyboard for button in row}
        assert 'Загрузить данные' in labels
        assert 'Выдача' not in labels
        assert '📝 Оставить заявку' not in labels
        assert '⚙️ Дополнительно' in labels
        print('REGISTRATION_ACCEPT_FLOW PASS')
    finally:
        for name, value in original.items():
            setattr(request_handlers, name, value)


async def verify_team_accept() -> None:
    original = {
        'load_json': team_handlers.load_json,
        'save_json': team_handlers.save_json,
    }

    async def load_json(path):
        if path == TEAM_REQUESTS_FILE:
            return {'100': {'name': 'Тест Пользователь', 'team': 'R LAMP'}}
        if path == TEAMS_FILE:
            return {}
        return {}

    team_handlers.load_json = load_json
    team_handlers.save_json = AsyncMock()
    try:
        query = FakeQuery('team_accept:100')
        context = FakeContext()
        result = await team_handlers.team_moderation_callback(SimpleNamespace(callback_query=query), context)
        assert result == ConversationHandler.END
        keyboard = context.bot.send_message.await_args.kwargs['reply_markup']
        labels = {button.text for row in keyboard.keyboard for button in row}
        assert 'Загрузить данные' in labels
        assert 'Выдача' not in labels
        assert '📝 Оставить заявку' not in labels
        print('TEAM_ACCEPT_FLOW PASS')
    finally:
        for name, value in original.items():
            setattr(team_handlers, name, value)


async def main() -> None:
    await verify_registration_accept()
    await verify_team_accept()


if __name__ == '__main__':
    asyncio.run(main())
