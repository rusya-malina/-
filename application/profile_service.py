from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from config import GROUPS_FILE, ISSUANCE_FILE, KPI_FILE, USERS_FILE
from data_models import make_user_record, user_name
from domain.models import OperationResult
from repositories.json_repository import JsonRepository, transaction


def normalize_profile_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


@dataclass
class ProfileService:
    """Atomically rename a registered employee across all linked JSON records."""

    users: JsonRepository
    groups: JsonRepository
    kpi: JsonRepository
    issuance: JsonRepository

    @classmethod
    def from_default_storage(cls) -> "ProfileService":
        return cls(
            users=JsonRepository(USERS_FILE),
            groups=JsonRepository(GROUPS_FILE),
            kpi=JsonRepository(KPI_FILE),
            issuance=JsonRepository(ISSUANCE_FILE),
        )

    async def rename(self, employee_id: int | str, new_name: str) -> OperationResult:
        employee_id = str(employee_id)
        new_name = str(new_name).strip()
        new_key = normalize_profile_name(new_name)
        if len(new_name) < 3 or len(new_name.split()) < 2 or not new_key:
            return OperationResult(False, "invalid_name", "invalid_employee_name")

        def mutate(files: dict[str, dict]) -> OperationResult:
            users = files[self.users.path]
            groups = files[self.groups.path]
            kpi = files[self.kpi.path]
            issuance = files[self.issuance.path]
            current = users.get(employee_id)
            if not isinstance(current, dict):
                return OperationResult(False, "not_found", "registered_user_not_found")

            old_name = user_name(current)
            old_key = normalize_profile_name(old_name)
            if old_key == new_key:
                return OperationResult(True, "unchanged", "profile_name_unchanged", (employee_id,), {"name": new_name})

            for other_id, record in users.items():
                if str(other_id) != employee_id and normalize_profile_name(user_name(record)) == new_key:
                    return OperationResult(False, "conflict", "employee_name_already_exists", details={"name": new_name})

            if new_key in kpi and new_key != old_key:
                return OperationResult(False, "conflict", "kpi_name_already_exists", details={"name": new_name})

            created_at = current.get("created_at")
            users[employee_id] = make_user_record(new_name, created_at=created_at)

            for record in groups.values():
                if isinstance(record, dict) and normalize_profile_name(user_name(record)) == old_key:
                    record["name"] = new_name

            kpi_record = kpi.pop(old_key, None)
            if isinstance(kpi_record, dict):
                kpi_record["original_name"] = new_name
                kpi[new_key] = kpi_record

            for key, record in issuance.items():
                if isinstance(record, dict) and (
                    str(key) == employee_id or normalize_profile_name(user_name(record)) == old_key
                ):
                    record["name"] = new_name

            return OperationResult(
                True,
                "updated",
                "profile_name_updated",
                (employee_id,),
                {"old_name": old_name, "name": new_name},
            )

        return await transaction((self.users.path, self.groups.path, self.kpi.path, self.issuance.path)).run(mutate)


__all__ = ["ProfileService", "normalize_profile_name"]
