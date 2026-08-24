from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handlers.admin as admin_handler
import handlers.user as user_handler
import permissions
from bot_context import ADMIN_ID, EXTRA_MENU_STATE, ConversationHandler
from keyboards import get_main_keyboard, get_team_menu_keyboard


def labels(markup):
    return {button.text for row in markup.keyboard for button in row}


async def main() -> None:
    with tempfile.NamedTemporaryFile(prefix="admin_session_", suffix=".json", delete=False) as session_file:
        session_path = session_file.name
    permissions.ADMIN_SESSION_FILE = session_path
    permissions._PERSISTENCE_LOADED = False
    permissions._PERSISTED_ADMIN_MODE = False
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

    message.reply_text.reset_mock()
    result = await user_handler.cancel_action(update, context)
    assert result == ConversationHandler.END
    back_admin_labels = labels(message.reply_text.await_args.kwargs['reply_markup'])
    assert 'Загрузить данные' in back_admin_labels
    assert '⚙️ Дополнительно' in back_admin_labels
    assert 'Моя команда' not in back_admin_labels

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

    original_get_group = admin_handler.get_user_group
    try:
        for user_id, group in ((700001, "coor A"), (700002, "coor R")):
            admin_handler.get_user_group = AsyncMock(return_value=group)
            coordinator_context = SimpleNamespace(user_data={"admin_mode": True})
            coordinator_message = SimpleNamespace(reply_text=AsyncMock())
            coordinator_update = SimpleNamespace(
                effective_user=SimpleNamespace(id=user_id),
                message=coordinator_message,
            )
            result = await admin_handler.exit_admin_mode(coordinator_update, coordinator_context)
            assert result == ConversationHandler.END
            coordinator_text = coordinator_message.reply_text.await_args.args[0]
            coordinator_labels = labels(coordinator_message.reply_text.await_args.kwargs["reply_markup"])
            assert group in coordinator_text
            assert "Моя команда" in coordinator_labels
            assert "Загрузить данные" not in coordinator_labels
            assert coordinator_context.user_data["admin_mode"] is False

        admin_handler.get_user_group = AsyncMock(return_value="A LAMP")
        employee_message = SimpleNamespace(reply_text=AsyncMock())
        employee_update = SimpleNamespace(
            effective_user=SimpleNamespace(id=700003),
            message=employee_message,
        )
        result = await admin_handler.exit_admin_mode(employee_update, SimpleNamespace(user_data={}))
        assert result == ConversationHandler.END
        assert "только координаторам" in employee_message.reply_text.await_args.args[0]
    finally:
        admin_handler.get_user_group = original_get_group

    Path(session_path).unlink(missing_ok=True)
    print('admin mode and SPV team menu tests passed')


if __name__ == '__main__':
    asyncio.run(main())
