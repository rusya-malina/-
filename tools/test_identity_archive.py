from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application.admin_service import EmployeeAdminService
from application.identity_service import IdentityService
from config import ADMIN_ID
from data_models import make_group_record, make_user_record
from repositories.json_repository import JsonRepository
from storage import load_json_sync, save_json_sync


async def test_delete_archives_all_employee_data_and_restore_removes_excel_alias() -> None:
    with tempfile.TemporaryDirectory(prefix="identity_archive_") as temp_dir:
        base = Path(temp_dir)
        users_path = str(base / "users.json")
        groups_path = str(base / "groups.json")
        kpi_path = str(base / "kpi.json")
        issuance_path = str(base / "issuance.json")
        deleted_path = str(base / "deleted_users.json")

        save_json_sync({"100": make_user_record("Иван Петров")}, users_path)
        save_json_sync({"100": make_group_record("Иван Петров", "R LAMP")}, groups_path)
        save_json_sync(
            {"иван петров": {"original_name": "Иван Петров", "gt_plan": 10, "gt_fact": 4}},
            kpi_path,
        )
        save_json_sync(
            {
                "_schema_version": 2,
                "100": {"name": "Иван Петров", "mints_issued": 7, "sticks_issued": 3, "history": []},
            },
            issuance_path,
        )
        save_json_sync({}, deleted_path)

        admin_service = EmployeeAdminService(
            users=JsonRepository(users_path),
            kpi=JsonRepository(kpi_path),
            groups=JsonRepository(groups_path),
            issuance=JsonRepository(issuance_path),
            deleted=JsonRepository(deleted_path),
        )
        deleted = await admin_service.delete_registered("100", ADMIN_ID)
        assert deleted.ok is True
        assert load_json_sync(users_path) == {}
        assert load_json_sync(groups_path) == {}
        assert "иван петров" not in load_json_sync(kpi_path)
        assert "100" not in load_json_sync(issuance_path)
        archive = load_json_sync(deleted_path)["100"]
        assert archive["user_record"]["name"] == "Иван Петров"
        assert archive["group_record"]["group"] == "R LAMP"
        assert "иван петров" in archive["kpi_records"]
        assert archive["issuance_records"]["100"]["mints_issued"] == 7

        # Simulate the next KPI/issuance import creating an Excel-only alias.
        save_json_sync({"excel_ivan_petrov": make_user_record("Иван Петров")}, users_path)
        save_json_sync({"excel_ivan_petrov": make_group_record("Иван Петров", "R LAMP")}, groups_path)
        save_json_sync(
            {"_schema_version": 2, "excel_ivan_petrov": {"name": "Иван Петров", "mints_issued": 1}},
            issuance_path,
        )

        identity_service = IdentityService(
            deleted=JsonRepository(deleted_path),
            users=JsonRepository(users_path),
            groups=JsonRepository(groups_path),
            kpi=JsonRepository(kpi_path),
            issuance=JsonRepository(issuance_path),
        )
        restored = await identity_service.restore_archived("100")
        assert restored.ok is True
        assert load_json_sync(users_path)["100"]["name"] == "Иван Петров"
        assert "excel_ivan_petrov" not in load_json_sync(users_path)
        assert load_json_sync(groups_path)["100"]["group"] == "R LAMP"
        assert "excel_ivan_petrov" not in load_json_sync(groups_path)
        assert load_json_sync(kpi_path)["иван петров"]["gt_fact"] == 4
        assert load_json_sync(issuance_path)["100"]["mints_issued"] == 7
        assert "excel_ivan_petrov" not in load_json_sync(issuance_path)
        assert "100" not in load_json_sync(deleted_path)


def main() -> None:
    asyncio.run(test_delete_archives_all_employee_data_and_restore_removes_excel_alias())
    print("IDENTITY_ARCHIVE PASS")


if __name__ == "__main__":
    main()
