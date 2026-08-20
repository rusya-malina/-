"""Contract tests for staged Excel import application use cases."""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application.import_service import ImportService
from repositories.json_repository import JsonRepository


def test_import_service() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        kpi_path = root / "kpi.json"
        issuance_path = root / "issuance.json"
        users_path = root / "users.json"
        for path in (kpi_path, issuance_path):
            path.write_text("{}", encoding="utf-8")
        users_path.write_text(
            json.dumps(
                {
                    "excel_old employee": {"name": "Old Employee"},
                    "excel_nan": {"name": "nan"},
                    "123": {"name": "Test Employee"},
                }
            ),
            encoding="utf-8",
        )
        service = ImportService(
            JsonRepository(str(kpi_path)),
            JsonRepository(str(issuance_path)),
            JsonRepository(str(users_path)),
        )

        async def scenario() -> None:
            kpi = await service.prepare_kpi_import(
                [
                    {
                        "full_name": "Test Employee",
                        "gt_plan": 90,
                        "gt_fact": 10,
                        "micro_plan": 128,
                        "micro_las_fact": 20,
                        "micro_lau_fact": 30,
                        "retrafic_plan": 15,
                        "retrafic_fact": 4,
                        "office_hours": 8,
                        "field_hours": 16,
                    }
                ]
            )
            assert kpi["new_names"] == []
            assert kpi["removed_names"] == ["Old Employee", "nan"]
            await service.apply_kpi_import(kpi)
            assert "test employee" in json.loads(kpi_path.read_text(encoding="utf-8"))
            users = json.loads(users_path.read_text(encoding="utf-8"))
            assert "excel_old employee" not in users
            assert users["123"]["name"] == "Test Employee"

            issuance = await service.prepare_issuance_import([("Test Employee", 10.0, 2.0)], 99)
            await service.apply_issuance_import(issuance)
            record = next(iter(json.loads(issuance_path.read_text(encoding="utf-8")).values()))
            assert record["mints_issued"] == 10.0
            assert record["sticks_issued"] == 2.0
            assert len(record["history"]) == 2

        asyncio.run(scenario())


if __name__ == "__main__":
    test_import_service()
    print("IMPORT_SERVICE PASS")
