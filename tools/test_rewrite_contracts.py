"""Contract tests for the first rewritten application/repository slice."""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application.admin_service import EmployeeAdminService
from application.employee_service import EmployeeService
from application.registration_service import RegistrationService
from application.report_service import ReportService
from config import ADMIN_ID
from data_models import make_group_record, make_user_record, registration_request
from repositories.json_repository import JsonRepository
from storage import load_json_sync, save_json_sync


async def test_admin_service_deletes_user_and_kpi_atomically() -> None:
    with tempfile.TemporaryDirectory(prefix="rewrite_admin_") as temp_dir:
        base = Path(temp_dir)
        users_path = str(base / "users.json")
        kpi_path = str(base / "kpi.json")
        save_json_sync({"100": make_user_record("Иван Петров")}, users_path)
        save_json_sync({"иван петров": {"original_name": "Иван Петров", "gt_fact": 1}}, kpi_path)
        service = EmployeeAdminService(JsonRepository(users_path), JsonRepository(kpi_path))
        denied = await service.delete_registered("100", ADMIN_ID + 1)
        assert denied.code == "forbidden"
        deleted = await service.delete_registered("100", ADMIN_ID)
        assert deleted.ok is True
        assert "100" not in load_json_sync(users_path)
        assert "иван петров" not in load_json_sync(kpi_path)


async def test_registration_service_uses_atomic_contract() -> None:
    with tempfile.TemporaryDirectory(prefix="rewrite_registration_") as temp_dir:
        base = Path(temp_dir)
        pending_path = str(base / "pending.json")
        users_path = str(base / "users.json")
        groups_path = str(base / "groups.json")
        issuance_path = str(base / "issuance.json")
        save_json_sync({"100": registration_request({"name": "Иван Петров", "group": "R LAMP"}, user_id="100")}, pending_path)
        save_json_sync(
            {"excel_ivan_petrov": make_user_record("Иван Петров")},
            users_path,
        )
        save_json_sync({"excel_ivan_petrov": make_group_record("Иван Петров", "R LAMP")}, groups_path)
        save_json_sync({"excel_ivan_petrov": {"mints_issued": 5, "sticks_issued": 2}}, issuance_path)
        service = RegistrationService(
            pending=JsonRepository(pending_path),
            users=JsonRepository(users_path),
            groups=JsonRepository(groups_path),
            issuance=JsonRepository(issuance_path),
        )

        accepted = await service.approve("100", ADMIN_ID)
        assert accepted.ok is True
        assert accepted.code == "accepted"
        assert load_json_sync(users_path)["100"]["name"] == "Иван Петров"
        assert "excel_ivan_petrov" not in load_json_sync(users_path)
        assert load_json_sync(groups_path)["100"]["group"] == "R LAMP"
        assert load_json_sync(issuance_path)["100"]["mints_issued"] == 5
        assert "excel_ivan_petrov" not in load_json_sync(issuance_path)
        assert accepted.details["migrated_aliases"] == ["excel_ivan_petrov"]
        assert "100" not in load_json_sync(pending_path)

        denied = await service.reject("missing", ADMIN_ID)
        assert denied.ok is False
        assert denied.code == "not_found"


async def test_report_service_uses_unified_issuance() -> None:
    with tempfile.TemporaryDirectory(prefix="rewrite_report_") as temp_dir:
        base = Path(temp_dir)
        users_path = str(base / "users.json")
        groups_path = str(base / "groups.json")
        kpi_path = str(base / "kpi.json")
        issuance_path = str(base / "issuance.json")
        save_json_sync({"100": make_user_record("Иван Петров")}, users_path)
        save_json_sync({"100": make_group_record("Иван Петров", "R LAMP")}, groups_path)
        save_json_sync({"Иван Петров": {"original_name": "Иван Петров", "gt_fact": 2, "micro_las_fact": 1, "micro_lau_fact": 1}}, kpi_path)
        save_json_sync({"_schema_version": 2, "100": {"mints_issued": 10, "sticks_issued": 5}}, issuance_path)
        employee_service = EmployeeService(
            users=JsonRepository(users_path),
            groups=JsonRepository(groups_path),
            kpi=JsonRepository(kpi_path),
            issuance=JsonRepository(issuance_path),
        )
        employee = (await employee_service.list_registry())[0]
        service = ReportService(
            users=JsonRepository(users_path),
            groups=JsonRepository(groups_path),
            kpi=JsonRepository(kpi_path),
            issuance=JsonRepository(issuance_path),
        )
        report = await service.personal_report(employee)
        assert report["balances"]["mints_balance"] == 8
        assert report["balances"]["sticks_balance"] == 3


async def test_employee_service_reads_unified_registry() -> None:
    with tempfile.TemporaryDirectory(prefix="rewrite_employee_") as temp_dir:
        base = Path(temp_dir)
        users_path = str(base / "users.json")
        groups_path = str(base / "groups.json")
        kpi_path = str(base / "kpi.json")
        issuance_path = str(base / "issuance.json")
        save_json_sync({"100": make_user_record("Иван Петров"), "excel_ivan": make_user_record("Иван Петров")}, users_path)
        save_json_sync({"100": make_group_record("Иван Петров", "R LAMP")}, groups_path)
        save_json_sync({"Иван Петров": {"original_name": "Иван Петров", "gt_plan": 1}}, kpi_path)
        save_json_sync({"_schema_version": 2}, issuance_path)
        service = EmployeeService(
            users=JsonRepository(users_path),
            groups=JsonRepository(groups_path),
            kpi=JsonRepository(kpi_path),
            issuance=JsonRepository(issuance_path),
        )
        registry = await service.list_registry()
        assert len(registry) == 1
        assert registry[0]["user_id"] == "100"
        assert "excel_ivan" in registry[0]["aliases"]
        assert (await service.find_by_id("excel_ivan"))["name"] == "Иван Петров"


async def main() -> None:
    await test_admin_service_deletes_user_and_kpi_atomically()
    await test_registration_service_uses_atomic_contract()
    await test_report_service_uses_unified_issuance()
    await test_employee_service_reads_unified_registry()
    print("REWRITE_CONTRACTS PASS")


if __name__ == "__main__":
    asyncio.run(main())
