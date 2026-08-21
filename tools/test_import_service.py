from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application.import_service import ImportSafetyError, ImportService, build_user_import_audit
from repositories.json_repository import JsonRepository


def test_import_service() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        kpi_path = root / "kpi.json"
        issuance_path = root / "issuance.json"
        users_path = root / "users.json"
        kpi_path.write_text(
            json.dumps(
                {
                    "old employee": {
                        "original_name": "Old Employee",
                        "gt_plan": 10,
                        "gt_fact": 5,
                    }
                }
            ),
            encoding="utf-8",
        )
        issuance_path.write_text("{}", encoding="utf-8")
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
            assert kpi["removed_names"] == []
            assert kpi["stale_names"] == ["Old Employee"]
            await service.apply_kpi_import(kpi)
            applied_kpi = json.loads(kpi_path.read_text(encoding="utf-8"))
            assert "test employee" in applied_kpi
            assert "old employee" in applied_kpi
            users = json.loads(users_path.read_text(encoding="utf-8"))
            assert "excel_old employee" in users
            assert users["123"]["name"] == "Test Employee"

            issuance = await service.prepare_issuance_import([("Test Employee", 10.0, 2.0)], 99)
            await service.apply_issuance_import(issuance)
            record = next(iter(json.loads(issuance_path.read_text(encoding="utf-8")).values()))
            assert record["mints_issued"] == 10.0
            assert record["sticks_issued"] == 2.0
            assert len(record["history"]) == 2

        asyncio.run(scenario())


def test_user_audit_and_decrease_guard() -> None:
    before = {"1": {"name": "Алиса Смирнова"}, "2": {"name": "Борис Петров"}}
    after = {"1": {"name": "Алиса Иванова"}, "3": {"name": "Вера Ким"}}
    audit = build_user_import_audit(before, after)
    assert audit["before_count"] == 2
    assert audit["after_count"] == 2
    assert audit["new_names"] == ["Вера Ким"]
    assert audit["removed_names"] == ["Борис Петров"]
    assert audit["changed_names"] == ["Алиса Смирнова → Алиса Иванова"]

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        kpi_path = root / "kpi.json"
        issuance_path = root / "issuance.json"
        users_path = root / "users.json"
        for path in (kpi_path, issuance_path, users_path):
            path.write_text("{}", encoding="utf-8")
        service = ImportService(
            JsonRepository(str(kpi_path)),
            JsonRepository(str(issuance_path)),
            JsonRepository(str(users_path)),
        )

        async def scenario() -> None:
            try:
                await service.apply_kpi_import(
                    {
                        "kpi_data": {},
                        "users_data": {},
                        "user_audit": {"before_count": 2, "after_count": 1},
                    }
                )
            except ImportSafetyError:
                return
            raise AssertionError("KPI import with fewer users must be rejected")

        asyncio.run(scenario())


if __name__ == "__main__":
    test_import_service()
    print("IMPORT_SERVICE PASS")
