from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from unittest.mock import AsyncMock, patch

import handlers.kpi as kpi_handler
from application.training_service import TrainingService
from config import GROUPS_FILE, ISSUANCE_FILE, KPI_FILE, TRAINING_HISTORY_FILE, USERS_FILE


def test_delivery_count_and_zero_value() -> None:
    history = {
        "100": {
            "deliveries": [
                {"type": "one", "month": "2026-08"},
                {"type": "two", "month": "2026-08"},
                {"type": "one", "month": "2026-07"},
            ]
        }
    }
    visible_users = [
        {"name": "Екатерина Харчевникова", "aliases": ["100", "excel_екатерина харчевникова"]},
        {"name": "Анна Смирнова", "aliases": ["200"]},
    ]

    report = kpi_handler.build_monthly_training_report(visible_users, history, "2026-08")

    assert "Екатерина Харчевникова — 2" in report
    assert "Анна Смирнова — 0" in report
    assert TrainingService.delivery_count_from_data(history, ["100"], "2026-07") == 1
    assert TrainingService.delivery_count_from_data(history, ["200"], "2026-08") == 0


def test_button_is_visible_only_for_coordinators() -> None:
    coor_a = {button.text for row in kpi_handler.my_kpi_markup("coor A", False).inline_keyboard for button in row}
    coor_r = {button.text for row in kpi_handler.my_kpi_markup("coor R", False).inline_keyboard for button in row}
    lamp = {button.text for row in kpi_handler.my_kpi_markup("A LAMP", False).inline_keyboard for button in row}

    assert "📚 Обучения" in coor_a
    assert "📚 Обучения" in coor_r
    assert "📚 Обучения" not in lamp


async def test_training_callback_inside_my_kpi() -> None:
    users = {"100": {"name": "Координатор"}}
    groups = {}
    kpi_data = {}
    issuance_data = {}
    history = {"200": {"deliveries": [{"type": "one", "month": "2026-08"}]}}

    async def fake_load(path):
        return {
            USERS_FILE: users,
            GROUPS_FILE: groups,
            KPI_FILE: kpi_data,
            ISSUANCE_FILE: issuance_data,
            TRAINING_HISTORY_FILE: history,
        }[path]

    query = SimpleNamespace(
        data="my_kpi_show_trainings",
        from_user=SimpleNamespace(id=100),
        answer=AsyncMock(),
        message=SimpleNamespace(edit_text=AsyncMock()),
    )
    update = SimpleNamespace(callback_query=query)
    context = SimpleNamespace(user_data={})
    visible_users = [
        {"name": "Подчинённый 1", "aliases": ["200"]},
        {"name": "Подчинённый 2", "aliases": ["300"]},
    ]

    with (
        patch("handlers.kpi.load_json", new=AsyncMock(side_effect=fake_load)),
        patch("handlers.kpi.get_user_group", new=AsyncMock(return_value="coor A")),
        patch("handlers.kpi.get_visible_users", return_value=visible_users),
        patch("handlers.kpi.is_admin_mode", return_value=False),
    ):
        await kpi_handler.my_kpi_callback(update, context)

    text = query.message.edit_text.await_args.args[0]
    assert "Подчинённый 1 — 1" in text
    assert "Подчинённый 2 — 0" in text
    assert query.answer.await_count == 1


async def main() -> None:
    test_delivery_count_and_zero_value()
    test_button_is_visible_only_for_coordinators()
    await test_training_callback_inside_my_kpi()
    print("MY_KPI_TRAINING PASS")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
