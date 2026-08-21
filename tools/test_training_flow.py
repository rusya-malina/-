from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from handlers.training import is_training_group, training_candidates, training_markup
from keyboards import get_main_keyboard


def _keyboard_text(keyboard) -> list[str]:
    return [button.text for row in keyboard.keyboard for button in row]


def test_training_visibility_and_scoped_candidates() -> None:
    assert is_training_group("coor A") is True
    assert is_training_group("coor R") is True
    assert is_training_group("MNG") is False
    assert is_training_group("A LAMP") is False

    coor_a_labels = _keyboard_text(get_main_keyboard(100, group="coor A"))
    coor_r_labels = _keyboard_text(get_main_keyboard(101, group="coor R"))
    lamp_labels = _keyboard_text(get_main_keyboard(102, group="A LAMP"))
    assert "Загрузить обучение" in coor_a_labels
    assert "Загрузить обучение" in coor_r_labels
    assert "Загрузить обучение" not in lamp_labels

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


if __name__ == "__main__":
    test_training_visibility_and_scoped_candidates()
    print("TRAINING_FLOW PASS")
