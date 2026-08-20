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
from bot_context import (
    ADMIN_ID,
    TEAM_REQUESTS_FILE,
    TEAMS_FILE,
    ConversationHandler,
)


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
        self.user_data = {"admin_mode": True}


async def verify_registration_accept() -> None:
    original = {
        'load_request_inbox': request_handlers.load_request_inbox,
        'load_pending': request_handlers.load_pending,
        'RegistrationService': request_handlers.RegistrationService,
    }
    request_handlers.load_request_inbox = AsyncMock(return_value=[{
        'id': 'registration:100',
        'kind': 'registration',
        'user_id': '100',
        'name': 'Тест Пользователь',
        'group': 'A LAMP',
        'text': 'Выбранная группа: A LAMP.',
    }])
    class FakeRegistrationService:
        @classmethod
        def from_default_storage(cls):
            return cls()

        async def approve(self, user_id, actor_id):
            assert str(actor_id) == str(ADMIN_ID)
            return SimpleNamespace(ok=True, details={'name': 'Тест Пользователь', 'group': 'A LAMP'})

    request_handlers.RegistrationService = FakeRegistrationService
    request_handlers.load_pending = AsyncMock(return_value={'100': {'name': 'Тест Пользователь', 'group': 'A LAMP'}})

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
        'TeamService': team_handlers.TeamService,
    }

    async def load_json(path):
        if path == TEAM_REQUESTS_FILE:
            return {'100': {'name': 'Тест Пользователь', 'team': 'R LAMP'}}
        if path == TEAMS_FILE:
            return {}
        return {}

    class FakeTeamService:
        @classmethod
        def from_default_storage(cls):
            return cls()

        async def accept_request(self, user_id):
            assert str(user_id) == '100'
            return SimpleNamespace(ok=True)

    team_handlers.load_json = load_json
    team_handlers.TeamService = FakeTeamService
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
