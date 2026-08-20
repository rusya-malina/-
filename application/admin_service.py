"""Administrative employee management use cases."""
from __future__ import annotations

from dataclasses import dataclass

from config import KPI_FILE, USERS_FILE
from domain.models import OperationResult
from repositories.json_repository import JsonRepository, transaction


@dataclass
class EmployeeAdminService:
    users: JsonRepository
    kpi: JsonRepository

    @classmethod
    def from_default_storage(cls) -> "EmployeeAdminService":
        return cls(users=JsonRepository(USERS_FILE), kpi=JsonRepository(KPI_FILE))

    async def delete_registered(self, employee_id: int | str, actor_id: int) -> OperationResult:
        from config import ADMIN_ID

        if str(actor_id) != str(ADMIN_ID):
            return OperationResult(False, "forbidden", "permission_denied")

        employee_id = str(employee_id)
        clean_name: str | None = None

        def mutate(files: dict[str, dict]) -> OperationResult:
            nonlocal clean_name
            if employee_id not in files[self.users.path]:
                return OperationResult(False, "not_found", "registered_user_not_found")
            raw_user = files[self.users.path].pop(employee_id)
            clean_name = str(raw_user.get("name", "") if isinstance(raw_user, dict) else raw_user).strip().lower()
            if clean_name:
                files[self.kpi.path].pop(clean_name, None)
            return OperationResult(True, "deleted", "registered_user_deleted", (employee_id,), {"name": clean_name or ""})

        return await transaction((self.users.path, self.kpi.path)).run(mutate)


__all__ = ["EmployeeAdminService"]
