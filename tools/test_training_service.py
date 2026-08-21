from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application.training_service import TRAINING_ONE, TRAINING_TWO, TrainingService
from repositories.json_repository import JsonRepository


def test_training_service_monthly_guard() -> None:
    with tempfile.TemporaryDirectory() as directory:
        history_path = Path(directory) / "training_history.json"
        service = TrainingService(JsonRepository(str(history_path)))

        async def scenario() -> None:
            first = await service.record_delivery(
                "100", "Сотрудник A", TRAINING_ONE, "900", month="2026-08", file_id="telegram-file-one"
            )
            duplicate = await service.record_delivery("100", "Сотрудник A", TRAINING_ONE, "900", month="2026-08")
            next_month = await service.record_delivery("100", "Сотрудник A", TRAINING_ONE, "900", month="2026-09")
            second_first = await service.record_delivery(
                "100", "Сотрудник A", TRAINING_TWO, "900", month="2026-08", file_id="telegram-file-two"
            )
            second_repeat = await service.record_delivery("100", "Сотрудник A", TRAINING_TWO, "900", month="2026-08")

            assert first.ok and first.code == "training_recorded"
            assert not duplicate.ok and duplicate.code == "training_one_already_sent"
            assert next_month.ok
            assert second_first.ok and second_repeat.ok
            assert await service.has_sent_this_month("100", TRAINING_ONE, "2026-08") is True
            assert await service.has_sent_this_month("100", TRAINING_ONE, "2026-10") is False
            data = json.loads(history_path.read_text(encoding="utf-8"))
            assert len(data["100"]["deliveries"]) == 4
            assert TrainingService.missing_types_from_data(data, "100", "2026-08") == ()
            data["200"] = {"deliveries": [{"type": TRAINING_ONE, "month": "2026-08"}]}
            assert TrainingService.missing_types_from_data(data, "200", "2026-08") == (TRAINING_TWO,)
            assert TrainingService.missing_types_from_data(data, "100", "2026-10") == (TRAINING_ONE, TRAINING_TWO)
            assert TrainingService.missing_types_from_data(data, "missing", "2026-08") == (TRAINING_ONE, TRAINING_TWO)
            assert TrainingService.latest_file_id_from_data(data, "100", TRAINING_ONE) == "telegram-file-one"
            assert TrainingService.latest_file_id_from_data(data, "100", TRAINING_TWO) == "telegram-file-two"
            assert TrainingService.latest_file_id_from_data(data, "missing", TRAINING_ONE) is None

        asyncio.run(scenario())


if __name__ == "__main__":
    test_training_service_monthly_guard()
    print("TRAINING_SERVICE PASS")
