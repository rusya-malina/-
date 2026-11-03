from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application.admin_service import EmployeeAdminService
from application.registration_service import RegistrationService
from config import ADMIN_ID
from data_models import make_group_record, make_user_record, registration_request
from repositories.json_repository import JsonRepository
from storage import load_json_sync, save_json_sync


async def test_delete_removes_personal_data_and_allows_new_registration() -> None:
    with tempfile.TemporaryDirectory(prefix="identity_delete_") as temp_dir:
        base = Path(temp_dir)
        paths = {name: str(base / f"{name}.json") for name in (
            "users", "groups", "kpi", "issuance", "deleted", "training", "visits",
            "work_status", "drafts", "pending", "user_requests", "team_requests", "teams", "kpi_archive",
        )}
        save_json_sync({"100": make_user_record("Иван Петров")}, paths["users"])
        save_json_sync({"100": make_group_record("Иван Петров", "R LAMP")}, paths["groups"])
        save_json_sync({"иван петров": {"original_name": "Иван Петров", "gt_fact": 4}}, paths["kpi"])
        save_json_sync(
            {"records": {"arc1": {"employee": {"telegram_id": "100", "name": "Иван Петров"}}}},
            paths["kpi_archive"],
        )
        save_json_sync({"_schema_version": 2, "100": {"name": "Иван Петров", "mints_issued": 7}}, paths["issuance"])
        save_json_sync({"100": {"deliveries": [{"type": "one"}]}}, paths["training"])
        save_json_sync({
            "bookings": {"b1": {"user_id": "100", "name": "Иван Петров", "status": "active"}},
            "history": [{"user_id": "100", "name": "Иван Петров", "action": "booked"}],
        }, paths["visits"])
        save_json_sync({"2026-11-03": {
            "employees": {"100": {"user_id": "100", "name": "Иван Петров", "status": "working"}},
            "invites": {"i1": {"sender_id": "100", "receiver_id": "200"}},
        }}, paths["work_status"])
        save_json_sync({"100": {"name": "Иван Петров"}}, paths["drafts"])
        save_json_sync({"100": registration_request({"name": "Иван Петров"}, user_id="100")}, paths["pending"])
        save_json_sync({"r1": {"user_id": "100", "name": "Иван Петров"}}, paths["user_requests"])
        save_json_sync({"100": {"user_id": "100", "name": "Иван Петров", "team": "A LAMP"}}, paths["team_requests"])
        save_json_sync({"100": {"name": "Иван Петров", "team": "R LAMP"}}, paths["teams"])
        save_json_sync({"100": {"legacy": True}}, paths["deleted"])

        service = EmployeeAdminService(
            users=JsonRepository(paths["users"]),
            kpi=JsonRepository(paths["kpi"]),
            groups=JsonRepository(paths["groups"]),
            issuance=JsonRepository(paths["issuance"]),
            deleted=JsonRepository(paths["deleted"]),
            kpi_archive=JsonRepository(paths["kpi_archive"]),
            training=JsonRepository(paths["training"]),
            visits=JsonRepository(paths["visits"]),
            work_status=JsonRepository(paths["work_status"]),
            drafts=JsonRepository(paths["drafts"]),
            pending=JsonRepository(paths["pending"]),
            user_requests=JsonRepository(paths["user_requests"]),
            team_requests=JsonRepository(paths["team_requests"]),
            teams=JsonRepository(paths["teams"]),
        )
        deleted = await service.delete_registered("100", ADMIN_ID)
        assert deleted.ok is True
        assert load_json_sync(paths["users"]) == {}
        assert load_json_sync(paths["groups"]) == {}
        assert load_json_sync(paths["kpi"]) == {}
        assert load_json_sync(paths["kpi_archive"]) == {"records": {}}
        assert load_json_sync(paths["issuance"]) == {"_schema_version": 2}
        assert load_json_sync(paths["training"]) == {}
        assert load_json_sync(paths["visits"]) == {"bookings": {}, "history": []}
        assert load_json_sync(paths["work_status"])["2026-11-03"] == {"employees": {}, "invites": {}}
        assert load_json_sync(paths["drafts"]) == {}
        assert load_json_sync(paths["pending"]) == {}
        assert load_json_sync(paths["user_requests"]) == {}
        assert load_json_sync(paths["team_requests"]) == {}
        assert load_json_sync(paths["teams"]) == {}
        assert load_json_sync(paths["deleted"]) == {}

        # The same Telegram account can now submit and receive a completely new profile.
        save_json_sync({"100": registration_request({"name": "Новый сотрудник", "group": "A LAMP"}, user_id="100")}, paths["pending"])
        registration = RegistrationService(
            pending=JsonRepository(paths["pending"]),
            users=JsonRepository(paths["users"]),
            groups=JsonRepository(paths["groups"]),
            issuance=JsonRepository(paths["issuance"]),
        )
        accepted = await registration.approve("100", ADMIN_ID)
        assert accepted.ok is True
        assert load_json_sync(paths["users"])["100"]["name"] == "Новый сотрудник"
        assert load_json_sync(paths["groups"])["100"]["group"] == "A LAMP"
        assert "100" not in load_json_sync(paths["pending"])


def main() -> None:
    asyncio.run(test_delete_removes_personal_data_and_allows_new_registration())
    print("IDENTITY_DELETE_REREGISTRATION PASS")


if __name__ == "__main__":
    main()
