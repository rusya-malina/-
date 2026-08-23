from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application.monthly_kpi_service import MonthlyKpiService, MonthlyKpiValidationError
from handlers.monthly_kpi import _monthly_kpi_markup
from repositories.json_repository import JsonRepository


def test_prepare_validates_and_normalizes() -> None:
    prepared = MonthlyKpiService.prepare(
        [
            {"name": "Продажи", "plan": 100, "weight": 60},
            {"name": " Качество ", "plan": 90, "weight": 40},
        ]
    )
    assert prepared["row_count"] == 2
    assert prepared["total_weight"] == 100
    assert prepared["metrics"][0]["key"] == "продажи"
    assert prepared["metrics"][1]["name"] == "Качество"

    normalized = MonthlyKpiService.prepare([{"name": "GT", "plan": 10, "weight": 50}])
    assert normalized["weights_adjusted"] is True
    assert normalized["original_total_weight"] == 50
    assert normalized["total_weight"] == 100
    assert normalized["metrics"][0]["weight"] == 100

    for rows, expected in (
        ([{"name": "GT", "plan": 10, "weight": 0}], "больше 0"),
        ([{"name": "GT", "plan": -1, "weight": 100}], "план не может"),
        ([{"name": "GT", "plan": 10, "weight": -1}], "вес не может"),
        ([{"name": "GT", "plan": 10, "weight": 50}, {"name": "gt", "plan": 10, "weight": 50}], "Дубликат"),
    ):
        try:
            MonthlyKpiService.prepare(rows)
        except MonthlyKpiValidationError as error:
            assert expected in str(error)
        else:
            raise AssertionError("Invalid monthly KPI must be rejected")


def test_preview_actions() -> None:
    labels = [
        button.text
        for row in _monthly_kpi_markup().inline_keyboard
        for button in row
    ]
    callbacks = [
        button.callback_data
        for row in _monthly_kpi_markup().inline_keyboard
        for button in row
    ]
    assert labels == [
        "✅ Загрузить сейчас",
        "📅 Загрузить в начале следующего месяца",
        "❌ Отмена",
    ]
    assert callbacks == ["monthly_kpi_now", "monthly_kpi_next", "monthly_kpi_cancel"]


def test_activate_now_and_schedule_next() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "plans.json"
        path.write_text("{}", encoding="utf-8")
        service = MonthlyKpiService(JsonRepository(str(path)))
        prepared = MonthlyKpiService.prepare(
            [
                {"name": "GT", "plan": 90, "weight": 40},
                {"name": "Микроакты", "plan": 128, "weight": 40},
                {"name": "Re-trafic", "plan": 15, "weight": 20},
            ]
        )

        async def scenario() -> None:
            active = await service.activate_now(prepared, period="2026-08")
            assert active["period"] == "2026-08"
            scheduled = await service.schedule_next(prepared, period="2026-09")
            assert scheduled["period"] == "2026-09"

        asyncio.run(scenario())
        stored = json.loads(path.read_text(encoding="utf-8"))
        assert stored["monthly_kpi"]["active"]["period"] == "2026-08"
        assert stored["monthly_kpi"]["pending"]["period"] == "2026-09"


if __name__ == "__main__":
    test_prepare_validates_and_normalizes()
    test_preview_actions()
    test_activate_now_and_schedule_next()
    print("MONTHLY_KPI_SERVICE PASS")
