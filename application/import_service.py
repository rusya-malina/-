"""Application use cases for staged Excel imports."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from config import ISSUANCE_FILE, KPI_FILE, LATEST_ISSUANCE_FILE, LATEST_KPI_FILE, USERS_FILE
from data_models import make_user_record, normalize_issuance_record, user_name
from repositories.json_repository import JsonRepository, transaction
from services import _normalize_person_name
from storage import replace_latest_file


@dataclass
class ImportService:
    """Builds and applies validated import snapshots without Telegram dependencies."""

    kpi: JsonRepository
    issuance: JsonRepository
    users: JsonRepository

    @classmethod
    def from_default_storage(cls) -> "ImportService":
        return cls(
            kpi=JsonRepository(KPI_FILE),
            issuance=JsonRepository(ISSUANCE_FILE),
            users=JsonRepository(USERS_FILE),
        )

    async def prepare_kpi_import(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        users_data = await self.users.load()
        valid_rows: list[dict[str, Any]] = []
        for row in rows:
            employee_name = str(row.get("full_name", "")).strip()
            normalized_name = _normalize_person_name(employee_name)
            if not normalized_name or normalized_name in {"nan", "none"}:
                continue
            valid_rows.append(row)
        latest_names = {_normalize_person_name(row["full_name"]) for row in valid_rows}
        removed_user_ids: list[str] = []
        removed_names: list[str] = []
        for employee_id, record in list(users_data.items()):
            employee_name = user_name(record)
            if str(employee_id).startswith("excel_") and _normalize_person_name(employee_name) not in latest_names:
                removed_user_ids.append(str(employee_id))
                removed_names.append(employee_name)
                users_data.pop(employee_id, None)

        existing_names = {_normalize_person_name(user_name(value)) for value in users_data.values()}
        kpi_data: dict[str, dict[str, Any]] = {}
        updated_names: list[str] = []
        new_names: list[str] = []
        updated_keys: set[str] = set()

        for row in valid_rows:
            employee_name = str(row["full_name"]).strip()
            clean_name = _normalize_person_name(employee_name)
            kpi_data[clean_name] = {
                "original_name": employee_name,
                "gt_plan": float(row["gt_plan"]),
                "gt_fact": float(row["gt_fact"]),
                "micro_plan": float(row["micro_plan"]),
                "micro_las_fact": float(row["micro_las_fact"]),
                "micro_lau_fact": float(row["micro_lau_fact"]),
                "retrafic_plan": float(row["retrafic_plan"]),
                "retrafic_fact": float(row["retrafic_fact"]),
                "office_hours": float(row["office_hours"]),
                "field_hours": float(row["field_hours"]),
            }
            if clean_name not in updated_keys:
                updated_names.append(employee_name)
                updated_keys.add(clean_name)
            if clean_name not in existing_names:
                fake_uid = f"excel_{clean_name}"
                users_data[fake_uid] = make_user_record(employee_name)
                existing_names.add(clean_name)
                new_names.append(employee_name)

        return {
            "kind": "kpi",
            "kpi_data": kpi_data,
            "users_data": users_data,
            "updated_names": updated_names,
            "new_names": new_names,
            "removed_user_ids": removed_user_ids,
            "removed_names": removed_names,
            "row_count": len(valid_rows),
        }

    async def prepare_issuance_import(
        self,
        rows: list[tuple[str, float, float]],
        admin_id: int | str,
    ) -> dict[str, Any]:
        users_data = await self.users.load()
        issuance_data = await self.issuance.load()
        name_to_user_id = {
            _normalize_person_name(user_name(value)): str(user_id)
            for user_id, value in users_data.items()
            if user_name(value) and _normalize_person_name(user_name(value)) != "nan"
        }
        added_without_telegram: list[str] = []
        timestamp = datetime.now(timezone.utc).isoformat()

        for employee_name, mints_amount, sticks_amount in rows:
            normalized_name = _normalize_person_name(employee_name)
            user_id = name_to_user_id.get(normalized_name)
            if not user_id:
                user_id = f"excel_{normalized_name.replace(' ', '_')}"
                suffix = 2
                while user_id in users_data and _normalize_person_name(user_name(users_data[user_id])) != normalized_name:
                    user_id = f"excel_{normalized_name.replace(' ', '_')}_{suffix}"
                    suffix += 1
                users_data[user_id] = make_user_record(employee_name)
                name_to_user_id[normalized_name] = user_id
                added_without_telegram.append(employee_name)

            record = normalize_issuance_record(issuance_data.get(user_id), name=employee_name)
            if mints_amount:
                record["mints_issued"] += float(mints_amount)
                record["history"].append(
                    {"type": "mints_excel", "amount": mints_amount, "admin_id": str(admin_id), "created_at": timestamp}
                )
            if sticks_amount:
                record["sticks_issued"] += float(sticks_amount)
                record["history"].append(
                    {"type": "sticks_excel", "amount": sticks_amount, "admin_id": str(admin_id), "created_at": timestamp}
                )
            issuance_data[user_id] = record

        return {
            "kind": "issuance",
            "users_data": users_data,
            "issuance_data": issuance_data,
            "row_count": len(rows),
            "added_without_telegram": added_without_telegram,
            "mints_total": sum(item[1] for item in rows),
            "sticks_total": sum(item[2] for item in rows),
        }

    async def apply_kpi_import(self, staged: dict[str, Any], source_path: str | None = None) -> None:
        kpi_data = staged["kpi_data"]
        users_data = staged["users_data"]

        def persist(files: dict[str, dict[str, Any]]) -> None:
            files[self.kpi.path].clear()
            files[self.kpi.path].update(kpi_data)
            for employee_id in staged.get("removed_user_ids", []):
                files[self.users.path].pop(employee_id, None)
            for employee_id, record in users_data.items():
                files[self.users.path].setdefault(employee_id, record)

        await transaction((self.kpi.path, self.users.path)).run(persist)
        if source_path:
            replace_latest_file(source_path, LATEST_KPI_FILE)

    async def apply_issuance_import(self, staged: dict[str, Any], source_path: str | None = None) -> None:
        users_data = staged["users_data"]
        issuance_data = staged["issuance_data"]

        def persist(files: dict[str, dict[str, Any]]) -> None:
            for employee_id, record in users_data.items():
                files[self.users.path].setdefault(employee_id, record)
            for employee_id, record in issuance_data.items():
                files[self.issuance.path][employee_id] = record

        await transaction((self.users.path, self.issuance.path)).run(persist)
        if source_path:
            replace_latest_file(source_path, LATEST_ISSUANCE_FILE)


__all__ = ["ImportService"]
