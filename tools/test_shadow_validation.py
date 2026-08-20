"""Shadow validation for application services against legacy-compatible calculations."""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application.issuance_service import IssuanceService
from application.kpi_service import KpiService
from application.team_service import TeamService
from repositories.json_repository import JsonRepository


def test_shadow_validation() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        kpi_path = root / "kpi.json"
        plans_path = root / "plans.json"
        issuance_path = root / "issuance.json"
        requests_path = root / "requests.json"
        teams_path = root / "teams.json"
        kpi_path.write_text("{}", encoding="utf-8")
        plans_path.write_text(json.dumps({"gt_plan": 90, "micro_plan": 128, "retrafic_plan": 15}), encoding="utf-8")
        issuance_path.write_text("{}", encoding="utf-8")
        requests_path.write_text("{}", encoding="utf-8")
        teams_path.write_text("{}", encoding="utf-8")

        async def scenario() -> None:
            kpi_service = KpiService(JsonRepository(str(kpi_path)), JsonRepository(str(plans_path)))
            legacy_kpi = {
                "original_name": "Shadow Employee",
                "gt_plan": 90.0,
                "gt_fact": 25.0,
                "micro_plan": 128.0,
                "micro_las_fact": 30.0,
                "micro_lau_fact": 40.0,
                "retrafic_plan": 15.0,
                "retrafic_fact": 5.0,
                "office_hours": 8.0,
                "field_hours": 16.0,
            }
            result = await kpi_service.save_manual_entry("Shadow Employee", legacy_kpi | {})
            assert result.ok
            assert result.details["record"] == legacy_kpi

            issuance_service = IssuanceService(JsonRepository(str(issuance_path)))
            result = await issuance_service.issue(7, "Shadow Employee", "mints", 12.5, 1)
            assert result.ok
            result = await issuance_service.issue(7, "Shadow Employee", "sticks", 3, 1)
            assert result.ok
            issuance = json.loads(issuance_path.read_text(encoding="utf-8"))["7"]
            assert issuance["mints_issued"] == 12.5
            assert issuance["sticks_issued"] == 3.0

            team_service = TeamService(JsonRepository(str(requests_path)), JsonRepository(str(teams_path)))
            created = await team_service.create_request(7, "Shadow Employee", "A LAMP")
            assert created.ok
            accepted = await team_service.accept_request(7)
            assert accepted.ok
            team = json.loads(teams_path.read_text(encoding="utf-8"))["7"]
            assert team["name"] == "Shadow Employee"
            assert team["team"] == "A LAMP"

        asyncio.run(scenario())


if __name__ == "__main__":
    test_shadow_validation()
    print("SHADOW_VALIDATION PASS")
