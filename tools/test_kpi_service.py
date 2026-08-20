"""Contract tests for KPI application use cases."""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application.kpi_service import KpiService
from repositories.json_repository import JsonRepository


def test_kpi_service() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        kpi_path = root / "kpi.json"
        plans_path = root / "plans.json"
        kpi_path.write_text("{}", encoding="utf-8")
        plans_path.write_text(json.dumps({"gt_plan": 90, "micro_plan": 128, "retrafic_plan": 15}), encoding="utf-8")
        service = KpiService(JsonRepository(str(kpi_path)), JsonRepository(str(plans_path)))

        async def scenario() -> None:
            result = await service.set_default_plans(
                {"gt_plan": "100", "micro_plan": 140, "retrafic_plan": "20"}
            )
            assert result.ok
            result = await service.save_manual_entry(
                "Test Employee",
                {
                    "gt_fact": 10,
                    "micro_las_fact": 20,
                    "micro_lau_fact": 30,
                    "retrafic_fact": 4,
                    "office_hours": 8,
                    "field_hours": 16,
                },
            )
            assert result.ok
            assert (await service.get_entry("test employee"))["gt_plan"] == 100.0
            assert await service.list_employee_names() == ["Test Employee"]
            invalid = await service.save_manual_entry("Test Employee", {"gt_fact": -1})
            assert not invalid.ok

        asyncio.run(scenario())


if __name__ == "__main__":
    test_kpi_service()
    print("KPI_SERVICE PASS")
