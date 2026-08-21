from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from domain.models import OperationResult
from handlers.training import (
    build_training_compliance_text,
    is_my_training_group,
    is_training_group,
    my_training_markup,
    process_training_file,
    training_candidates,
    training_markup,
    training_type_callback,
)
from keyboards import get_main_keyboard
from states import TRAINING_EMPLOYEE, TRAINING_TYPE


def _keyboard_text(keyboard) -> list[str]:
    return [button.text for row in keyboard.keyboard for button in row]


def test_training_visibility_and_scoped_candidates() -> None:
    assert is_training_group("coor A") is True
    assert is_training_group("coor R") is True
    assert is_training_group("MNG") is False
    assert is_training_group("A LAMP") is False
    assert is_my_training_group("A LAMP") is True
    assert is_my_training_group("R LAMP") is True
    assert is_my_training_group("coor A") is False

    coor_a_labels = _keyboard_text(get_main_keyboard(100, group="coor A"))
    coor_r_labels = _keyboard_text(get_main_keyboard(101, group="coor R"))
    lamp_labels = _keyboard_text(get_main_keyboard(102, group="A LAMP"))
    assert "Загрузить обучение" in coor_a_labels
    assert "Загрузить обучение" in coor_r_labels
    assert "Загрузить обучение" not in lamp_labels
    assert "Мои обучения" in lamp_labels

    my_markup = my_training_markup()
    my_callbacks = [button.callback_data for row in my_markup.inline_keyboard for button in row]
    assert my_callbacks == ["my_training:one", "my_training:two"]

    candidates = training_candidates(
        [
            {"name": "Сотрудник R", "group": "R LAMP", "aliases": ["excel_r", "200"]},
            {"name": "Без Telegram", "group": "A LAMP", "aliases": ["excel_a"]},
            {"name": "Сотрудник A", "group": "A LAMP", "aliases": ["100"]},
        ]
    )
    assert [item["name"] for item in candidates] == ["Сотрудник A", "Сотрудник R"]
    assert [item["user_id"] for item in candidates] == ["100", "200"]

    markup = training_markup(candidates)
    callback_data = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert callback_data == ["training_user:100", "training_user:200"]

    compliance = build_training_compliance_text(
        "coor A",
        [
            {"user_id": "100", "name": "Сотрудник A"},
            {"user_id": "200", "name": "Сотрудник B"},
            {"user_id": "300", "name": "Сотрудник C"},
        ],
        {
            "100": {"deliveries": [{"type": "one", "month": "2026-08"}]},
            "300": {
                "deliveries": [
                    {"type": "one", "month": "2026-08"},
                    {"type": "two", "month": "2026-08"},
                ]
            },
        },
        "2026-08",
    )
    assert "Сотрудник A — не проведено обучение: **2**" in compliance
    assert "Сотрудник B — не проведено обучение: **1, 2**" in compliance
    assert "Сотрудник C" not in compliance


def test_training_one_guard_message() -> None:
    query = SimpleNamespace(data="training_type:one", answer=AsyncMock())
    update = SimpleNamespace(callback_query=query)
    service = SimpleNamespace(has_sent_this_month=AsyncMock(return_value=True))
    context = SimpleNamespace(user_data={"training_recipient_id": "100", "training_recipient_name": "Сотрудник A"})

    async def scenario() -> int:
        with patch("handlers.training.TrainingService.from_default_storage", return_value=service):
            return await training_type_callback(update, context)

    result = asyncio.run(scenario())
    assert result == TRAINING_TYPE
    query.answer.assert_awaited_once_with(
        "Обучение один уже отправлено в этом месяце. Выберите обучение два",
        show_alert=True,
    )


def test_training_two_guard_message() -> None:
    query = SimpleNamespace(data="training_type:two", answer=AsyncMock())
    update = SimpleNamespace(callback_query=query)
    service = SimpleNamespace(has_sent_this_month=AsyncMock(return_value=True))
    context = SimpleNamespace(user_data={"training_recipient_id": "100", "training_recipient_name": "Сотрудник A"})

    async def scenario() -> int:
        with patch("handlers.training.TrainingService.from_default_storage", return_value=service):
            return await training_type_callback(update, context)

    result = asyncio.run(scenario())
    assert result == TRAINING_TYPE
    query.answer.assert_awaited_once_with(
        "Обучение два уже отправлено в этом месяце. Выберите обучение один",
        show_alert=True,
    )


def test_training_upload_returns_to_employee_list() -> None:
    candidates = [{"user_id": "100", "name": "Сотрудник A", "group": "A LAMP"}]
    document = SimpleNamespace(file_name="training.xlsx", file_id="telegram-file-one")
    message = SimpleNamespace(
        chat_id=900,
        message_id=901,
        document=document,
        reply_text=AsyncMock(),
    )
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=500))
    context = SimpleNamespace(
        user_data={
            "training_recipient_id": "100",
            "training_recipient_name": "Сотрудник A",
            "training_type": "one",
        },
        bot=SimpleNamespace(copy_message=AsyncMock(), send_message=AsyncMock()),
    )
    service = SimpleNamespace(
        record_delivery=AsyncMock(return_value=OperationResult(True, "training_recorded", "training_recorded"))
    )

    async def scenario() -> int:
        with (
            patch("handlers.training._visible_training_candidates", new=AsyncMock(return_value=("coor A", candidates))),
            patch("handlers.training._save_latest_training_file", new=AsyncMock()),
            patch("handlers.training.sync_training_history", new=AsyncMock()),
            patch("handlers.training.TrainingService.from_default_storage", return_value=service),
        ):
            return await process_training_file(update, context)

    result = asyncio.run(scenario())
    assert result == TRAINING_EMPLOYEE
    assert context.user_data == {}
    reply_markup = message.reply_text.await_args_list[-1].kwargs["reply_markup"]
    assert [button.text for row in reply_markup.inline_keyboard for button in row] == ["Сотрудник A"]
    service.record_delivery.assert_awaited_once_with("100", "Сотрудник A", "one", 500, file_id="telegram-file-one")


if __name__ == "__main__":
    test_training_visibility_and_scoped_candidates()
    test_training_one_guard_message()
    test_training_two_guard_message()
    test_training_upload_returns_to_employee_list()
    print("TRAINING_FLOW PASS")
