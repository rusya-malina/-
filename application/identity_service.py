"""Identity archive use cases for previously registered Telegram users."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from config import DELETED_USERS_FILE, GROUPS_FILE, ISSUANCE_FILE, KPI_FILE, USERS_FILE
from domain.models import OperationResult
from repositories.json_repository import JsonRepository, transaction


@dataclass
class IdentityService:
    """Owns archived identity lookup and restoration after an admin delete."""

    deleted: JsonRepository
    users: JsonRepository
    groups: JsonRepository
    kpi: JsonRepository
    issuance: JsonRepository

    @classmethod
    def from_default_storage(cls) -> "IdentityService":
        return cls(
            deleted=JsonRepository(DELETED_USERS_FILE),
            users=JsonRepository(USERS_FILE),
            groups=JsonRepository(GROUPS_FILE),
            kpi=JsonRepository(KPI_FILE),
            issuance=JsonRepository(ISSUANCE_FILE),
        )

    async def get_archived(self, user_id: int | str) -> dict[str, Any] | None:
        records = await self.deleted.load()
        record = records.get(str(user_id))
        return record if isinstance(record, dict) else None

    async def restore_archived(self, user_id: int | str) -> OperationResult:
        telegram_id = str(user_id)

        def mutate(files: dict[str, dict[str, Any]]) -> OperationResult:
            archive = files[self.deleted.path].get(telegram_id)
            if not isinstance(archive, dict):
                return OperationResult(False, "not_found", "archived_identity_not_found")
            if telegram_id in files[self.users.path]:
                files[self.deleted.path].pop(telegram_id, None)
                return OperationResult(True, "already_active", "identity_already_active", (telegram_id,))

            user_record = archive.get("user_record")
            if not isinstance(user_record, dict):
                return OperationResult(False, "invalid_archive", "archived_identity_invalid")
            normalized_name = _normalize_name(archive.get("name", user_record.get("name", "")))
            for key, record in list(files[self.users.path].items()):
                if str(key).startswith("excel_") and _normalize_name(record.get("name", key)) == normalized_name:
                    files[self.users.path].pop(key, None)
            files[self.users.path][telegram_id] = user_record

            group_record = archive.get("group_record")
            if isinstance(group_record, dict):
                for key, record in list(files[self.groups.path].items()):
                    if str(key).startswith("excel_") and _normalize_name(record.get("name", key)) == normalized_name:
                        files[self.groups.path].pop(key, None)
                files[self.groups.path][telegram_id] = group_record

            for key, record in (archive.get("kpi_records") or {}).items():
                if key not in files[self.kpi.path]:
                    files[self.kpi.path][key] = record
            for key, record in (archive.get("issuance_records") or {}).items():
                if key not in files[self.issuance.path]:
                    files[self.issuance.path][key] = record
            for key in list(files[self.issuance.path]):
                if str(key).startswith("excel_") and _normalize_name(files[self.issuance.path][key].get("name", key)) == normalized_name:
                    files[self.issuance.path].pop(key, None)

            files[self.deleted.path].pop(telegram_id, None)
            return OperationResult(
                True,
                "restored",
                "archived_identity_restored",
                (telegram_id,),
                {"name": archive.get("name", ""), "group": archive.get("group", "")},
            )

        return await transaction(
            (self.deleted.path, self.users.path, self.groups.path, self.kpi.path, self.issuance.path)
        ).run(mutate)


def _normalize_name(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


__all__ = ["IdentityService"]
