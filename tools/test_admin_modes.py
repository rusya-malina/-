from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handlers.admin as admin_handler
from bot_context import ADMIN_ID, EXTRA_MENU_STATE, ConversationHandler
from keyboards import get_main_keyboard, get_team_menu_keyboard


def labels(markup):
    return {button.text for row in markup.keyboard for button in row}


async def main() -> None:
    context = SimpleNamespace(user_data={})
    message = SimpleNamespace(reply_text=AsyncMock())
    update = SimpleNamespace(effective_user=SimpleNamespace(id=ADMIN_ID), message=message)

    result = await admin_handler.enter_admin_mode(update, context)
    assert result == ConversationHandler.END
    admin_markup = message.reply_text.await_args.kwargs['reply_markup']
    admin_labels = labels(admin_markup)
    assert context.user_data['admin_mode'] is True
    assert 'Загрузить данные' in admin_labels
    assert '⚙️ Дополнительно' in admin_labels
    assert 'Моя команда' not in admin_labels

    message.reply_text.reset_mock()
    result = await admin_handler.open_extra_menu(update, context)
    assert result == EXTRA_MENU_STATE
    assert message.reply_text.await_count == 1

    context.user_data['admin_mode'] = False
    message.reply_text.reset_mock()
    result = await admin_handler.open_extra_menu(update, context)
    assert result == ConversationHandler.END
    assert 'нет доступа' in message.reply_text.await_args.args[0]

    message.reply_text.reset_mock()
    result = await admin_handler.exit_admin_mode(update, context)
    assert result == ConversationHandler.END
    coor_markup = message.reply_text.await_args.kwargs['reply_markup']
    coor_labels = labels(coor_markup)
    assert context.user_data['admin_mode'] is False
    assert 'Моя команда' in coor_labels
    assert 'Загрузить данные' not in coor_labels
    assert '📢 Рассылка' not in coor_labels
    spv_labels = labels(get_main_keyboard(777777, "SPV"))
    assert "Моя команда" in spv_labels
    team_menu_labels = labels(get_team_menu_keyboard())
    assert "📊 KPI команды" in team_menu_labels
    assert "📦 Остатки команды" in team_menu_labels

    print('admin mode and SPV team menu tests passed')


if __name__ == '__main__':
    asyncio.run(main())
