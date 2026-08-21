"""Administrative employee management use cases."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from config import DELETED_USERS_FILE, GROUPS_FILE, ISSUANCE_FILE, KPI_FILE, USERS_FILE
from data_models import group_name, user_name
from domain.models import OperationResult
from repositories.json_repository import JsonRepository, transaction


@dataclass
class EmployeeAdminService:
    users: JsonRepository
    kpi: JsonRepository
    groups: JsonRepository | None = None
    issuance: JsonRepository | None = None
    deleted: JsonRepository | None = None

    @classmethod
    def from_default_storage(cls) -> "EmployeeAdminService":
        return cls(
            users=JsonRepository(USERS_FILE),
            kpi=JsonRepository(KPI_FILE),
            groups=JsonRepository(GROUPS_FILE),
            issuance=JsonRepository(ISSUANCE_FILE),
            deleted=JsonRepository(DELETED_USERS_FILE),
        )

    async def delete_registered(self, employee_id: int | str, actor_id: int) -> OperationResult:
        from config import ADMIN_ID

        if str(actor_id) != str(ADMIN_ID):
            return OperationResult(False, "forbidden", "permission_denied")

        employee_id = str(employee_id)
        clean_name: str | None = None
        archived_group = ""
        archived_kpi: dict[str, Any] = {}
        archived_issuance: dict[str, Any] = {}
        removed_aliases: list[str] = []

        paths = [self.users.path, self.kpi.path]
        optional_repositories = (self.groups, self.issuance, self.deleted)
        paths.extend(repository.path for repository in optional_repositories if repository is not None)

        def mutate(files: dict[str, dict[str, Any]]) -> OperationResult:
            nonlocal clean_name, archived_group, archived_kpi, archived_issuance
            raw_user = files[self.users.path].get(employee_id)
            if raw_user is None:
                return OperationResult(False, "not_found", "registered_user_not_found")

            clean_name = _normalize_name(user_name(raw_user, employee_id))
            raw_group = files.get(self.groups.path, {}).get(employee_id, {}) if self.groups is not None else {}
            archived_group = group_name(raw_group) or ""
            files[self.users.path].pop(employee_id, None)
            removed_aliases.append(employee_id)

            for key, record in list(files[self.kpi.path].items()):
                record_name = record.get("original_name", key) if isinstance(record, dict) else key
                if _normalize_name(record_name) == clean_name:
                    archived_kpi[key] = record
                    files[self.kpi.path].pop(key, None)

            if self.groups is not None:
                for key, record in list(files[self.groups.path].items()):
                    if key == employee_id or _normalize_name(user_name(record, key)) == clean_name:
                        if key == employee_id and isinstance(record, dict):
                            raw_group = record
                            archived_group = group_name(record) or archived_group
                        files[self.groups.path].pop(key, None)
                        if key not in removed_aliases:
                            removed_aliases.append(key)

            if self.issuance is not None:
                for key, record in list(files[self.issuance.path].items()):
                    if key == "_schema_version":
                        continue
                    if key == employee_id or _normalize_name(user_name(record, key)) == clean_name:
                        archived_issuance[key] = record
                        files[self.issuance.path].pop(key, None)
                        if key not in removed_aliases:
                            removed_aliases.append(key)

            if self.deleted is not None and employee_id.isdigit():
                files[self.deleted.path][employee_id] = {
                    "schema_version": 1,
                    "telegram_id": employee_id,
                    "name": user_name(raw_user, employee_id),
                    "group": archived_group,
                    "user_record": raw_user,
                    "group_record": raw_group if isinstance(raw_group, dict) else {},
                    "kpi_records": archived_kpi,
                    "issuance_records": archived_issuance,
                    "deleted_at": datetime.now(timezone.utc).isoformat(),
                    "reason": "admin_delete",
                }

            return OperationResult(
                True,
                "deleted",
                "registered_user_deleted",
                (employee_id,),
                {
                    "name": clean_name or "",
                    "group": archived_group,
                    "removed_aliases": removed_aliases,
                    "identity_archived": self.deleted is not None and employee_id.isdigit(),
                },
            )

        return await transaction(paths).run(mutate)


def _normalize_name(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


__all__ = ["EmployeeAdminService"]
