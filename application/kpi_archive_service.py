"""Archive and restore use cases for manually removed KPI records."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from config import BOT_TIMEZONE, GROUPS_FILE, KPI_ARCHIVE_FILE, KPI_FILE, USERS_FILE
from data_models import group_name, user_name
from domain.models import OperationResult
from repositories.json_repository import JsonRepository, transaction


def _normalize_name(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _empty_archive() -> dict[str, Any]:
    return {"schema_version": 1, "records": {}}


def _now() -> str:
    return datetime.now(ZoneInfo(BOT_TIMEZONE)).isoformat()


@dataclass
class KpiArchiveService:
    """Own the reversible lifecycle of KPI-only deletions."""

    kpi: JsonRepository
    archive: JsonRepository
    users: JsonRepository
    groups: JsonRepository

    @classmethod
    def from_default_storage(cls) -> "KpiArchiveService":
        return cls(
            kpi=JsonRepository(KPI_FILE),
            archive=JsonRepository(KPI_ARCHIVE_FILE),
            users=JsonRepository(USERS_FILE),
            groups=JsonRepository(GROUPS_FILE),
        )

    async def archive_entry(
        self,
        name: str,
        actor_id: int | str,
        *,
        reason: str = "removed_from_kpi",
    ) -> OperationResult:
        key = _normalize_name(name)
        users = await self.users.load()
        groups = await self.groups.load()
        employee = None
        for user_id, record in users.items():
            if _normalize_name(user_name(record)) == key:
                employee = {
                    "telegram_id": str(user_id) if str(user_id).isdigit() else None,
                    "name": user_name(record),
                    "group": group_name(groups.get(str(user_id))) or None,
                    "source": "registered_user",
                }
                break

        archive_id = f"kpi_arc_{datetime.now(ZoneInfo(BOT_TIMEZONE)).strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
        deleted_at = _now()

        def mutate(files: dict[str, dict[str, Any]]) -> OperationResult:
            active = files[self.kpi.path]
            record = active.get(key)
            if not isinstance(record, dict):
                return OperationResult(False, "not_found", "kpi_entry_not_found", (key,))
            archive = files[self.archive.path]
            if not isinstance(archive, dict):
                archive = _empty_archive()
                files[self.archive.path] = archive
            archive.setdefault("schema_version", 1)
            records = archive.setdefault("records", {})
            records[archive_id] = {
                "archive_id": archive_id,
                "status": "archived",
                "employee": employee or {
                    "telegram_id": None,
                    "name": record.get("original_name", name),
                    "group": None,
                    "source": "kpi_only",
                },
                "kpi": {
                    "original_name": record.get("original_name", name),
                    "period": record.get("period") or record.get("month"),
                    "record": deepcopy(record),
                },
                "deletion": {
                    "deleted_at": deleted_at,
                    "deleted_by": str(actor_id),
                    "reason": reason,
                    "source_action": "delete_from_list",
                },
                "restore": {
                    "restored_at": None,
                    "restored_by": None,
                    "restore_count": 0,
                    "last_conflict": None,
                },
            }
            active.pop(key, None)
            return OperationResult(
                True,
                "archived",
                "kpi_entry_archived",
                (key,),
                {"archive_id": archive_id, "name": record.get("original_name", name)},
            )

        return await transaction((self.kpi.path, self.archive.path)).run(mutate)

    async def list_archived(self) -> list[dict[str, Any]]:
        data = await self.archive.load()
        records = data.get("records", {}) if isinstance(data, dict) else {}
        result = [record for record in records.values() if isinstance(record, dict) and record.get("status") == "archived"]
        return sorted(result, key=lambda item: item.get("deletion", {}).get("deleted_at", ""), reverse=True)

    async def get_archived(self, archive_id: str) -> dict[str, Any] | None:
        data = await self.archive.load()
        record = data.get("records", {}).get(str(archive_id)) if isinstance(data, dict) else None
        return record if isinstance(record, dict) else None

    async def restore_entry(self, archive_id: str, actor_id: int | str) -> OperationResult:
        archive_id = str(archive_id)
        restored_at = _now()

        def mutate(files: dict[str, dict[str, Any]]) -> OperationResult:
            archive = files[self.archive.path]
            record = archive.get("records", {}).get(archive_id)
            if not isinstance(record, dict) or record.get("status") != "archived":
                return OperationResult(False, "not_found", "kpi_archive_entry_not_found", (archive_id,))
            kpi_record = record.get("kpi", {}).get("record")
            original_name = record.get("kpi", {}).get("original_name")
            key = _normalize_name(original_name)
            if not isinstance(kpi_record, dict) or not key:
                return OperationResult(False, "invalid_archive", "kpi_archive_entry_invalid", (archive_id,))
            active = files[self.kpi.path]
            if key in active:
                conflict = {"at": restored_at, "reason": "active_record_exists"}
                record.setdefault("restore", {})["last_conflict"] = conflict
                return OperationResult(False, "conflict", "kpi_restore_conflict", (archive_id,), conflict)
            active[key] = deepcopy(kpi_record)
            restore = record.setdefault("restore", {})
            restore.update({"restored_at": restored_at, "restored_by": str(actor_id), "restore_count": int(restore.get("restore_count", 0)) + 1, "last_conflict": None})
            record["status"] = "restored"
            return OperationResult(True, "restored", "kpi_entry_restored", (key,), {"archive_id": archive_id, "name": original_name})

        return await transaction((self.kpi.path, self.archive.path)).run(mutate)


__all__ = ["KpiArchiveService"]
