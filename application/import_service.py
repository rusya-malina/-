"""Application service for staged, non-destructive Excel imports."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from config import GROUPS_FILE, ISSUANCE_FILE, KPI_FILE, LATEST_ISSUANCE_FILE, LATEST_KPI_FILE, USERS_FILE
from data_models import make_group_record, make_user_record, normalize_issuance_record, user_name
from repositories.json_repository import JsonRepository, transaction
from services import _normalize_person_name
from storage import replace_latest_file

SOURCE_GROUPS = frozenset({"A LAMP", "R LAMP"})
MANAGEMENT_GROUPS = frozenset({"coor A", "coor R", "SPV", "MNG"})
_GROUP_ALIASES = {
    "a lamp": "A LAMP",
    "r lamp": "R LAMP",
    "coor a": "coor A",
    "coor r": "coor R",
    "коор a": "coor A",
    "коор р": "coor R",
    "spv": "SPV",
    "mng": "MNG",
}


def _issuance_name_key(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _issuance_token_key(value: Any) -> str:
    return " ".join(sorted(_issuance_name_key(value).split()))


def _group_from_row(row: dict[str, Any]) -> str | None:
    for key, value in row.items():
        normalized_key = str(key or "").strip().casefold().replace(" ", "_")
        if normalized_key not in {"group", "team", "группа", "команда", "уровень"}:
            continue
        normalized_value = str(value or "").strip().casefold()
        return _GROUP_ALIASES.get(normalized_value)
    return None


def build_user_import_audit(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_names = {str(user_id): user_name(record) for user_id, record in before.items()}
    after_names = {str(user_id): user_name(record) for user_id, record in after.items()}
    new_ids = sorted(set(after_names) - set(before_names))
    removed_ids = sorted(set(before_names) - set(after_names))
    changed_ids = sorted(
        user_id
        for user_id in set(before_names) & set(after_names)
        if _normalize_person_name(before_names[user_id]) != _normalize_person_name(after_names[user_id])
    )
    return {
        "before_count": len(before_names),
        "after_count": len(after_names),
        "new_names": [after_names[user_id] for user_id in new_ids],
        "removed_names": [before_names[user_id] for user_id in removed_ids],
        "changed_names": [f"{before_names[user_id]} → {after_names[user_id]}" for user_id in changed_ids],
        "removed_user_ids": removed_ids,
    }


class ImportSafetyError(ValueError):
    """Raised when an import would reduce or remove registered users."""


@dataclass
class ImportService:
    """Builds and applies validated import snapshots without destructive cleanup."""

    kpi: JsonRepository
    issuance: JsonRepository
    users: JsonRepository
    groups: JsonRepository | None = None

    @classmethod
    def from_default_storage(cls) -> "ImportService":
        return cls(
            kpi=JsonRepository(KPI_FILE),
            issuance=JsonRepository(ISSUANCE_FILE),
            users=JsonRepository(USERS_FILE),
            groups=JsonRepository(GROUPS_FILE),
        )

    async def prepare_kpi_import(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        users_data = await self.users.load()
        existing_kpi = await self.kpi.load()
        groups_data = await self.groups.load() if self.groups is not None else {}
        users_before = dict(users_data)
        valid_rows: list[dict[str, Any]] = []
        for row in rows:
            employee_name = str(row.get("full_name", "")).strip()
            normalized_name = _normalize_person_name(employee_name)
            if not normalized_name or normalized_name in {"nan", "none"}:
                continue
            valid_rows.append(row)

        latest_names = {_normalize_person_name(row["full_name"]) for row in valid_rows}
        existing_names = {_normalize_person_name(user_name(value)) for value in users_data.values()}
        name_to_user_id = {
            _normalize_person_name(user_name(value)): str(user_id)
            for user_id, value in users_data.items()
            if _normalize_person_name(user_name(value)) not in {"", "nan"}
        }
        group_by_name = {
            _normalize_person_name(user_name(record)): str(record.get("group") or record.get("team") or "").strip()
            for record in groups_data.values()
            if isinstance(record, dict) and user_name(record)
        }
        kpi_data: dict[str, dict[str, Any]] = dict(existing_kpi)
        updated_names: list[str] = []
        new_names: list[str] = []
        unresolved_team_names: list[str] = []
        updated_keys: set[str] = set()
        stale_names = sorted(
            {
                str(record.get("original_name", key))
                for key, record in existing_kpi.items()
                if isinstance(record, dict)
                and _normalize_person_name(record.get("original_name", key)) not in latest_names
            },
            key=str.casefold,
        )

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
            employee_id = name_to_user_id.get(clean_name)
            if not employee_id:
                employee_id = f"excel_{clean_name.replace(' ', '_')}"
                users_data.setdefault(employee_id, make_user_record(employee_name))
                name_to_user_id[clean_name] = employee_id
                existing_names.add(clean_name)
                new_names.append(employee_name)

            row_group = _group_from_row(row)
            assigned_group = row_group or group_by_name.get(clean_name)
            if assigned_group in MANAGEMENT_GROUPS:
                raise ImportSafetyError(
                    f"KPI import contains management employee: {employee_name} ({assigned_group})"
                )
            if assigned_group:
                groups_data[employee_id] = make_group_record(employee_name, assigned_group)
                group_by_name[clean_name] = assigned_group
            elif clean_name not in unresolved_team_names:
                unresolved_team_names.append(employee_name)

        user_audit = build_user_import_audit(users_before, users_data)
        return {
            "kind": "kpi",
            "kpi_data": kpi_data,
            "users_data": users_data,
            "groups_data": groups_data,
            "updated_names": updated_names,
            "new_names": new_names,
            "unresolved_team_names": unresolved_team_names,
            "removed_user_ids": user_audit["removed_user_ids"],
            "removed_names": user_audit["removed_names"],
            "stale_names": stale_names,
            "row_count": len(valid_rows),
            "user_audit": user_audit,
        }

    async def prepare_issuance_import(
        self,
        rows: list[tuple[str, float, float]],
        admin_id: int | str,
    ) -> dict[str, Any]:
        users_data = await self.users.load()
        issuance_data = await self.issuance.load()
        name_to_user_id = {
            _issuance_name_key(user_name(value)): str(user_id)
            for user_id, value in users_data.items()
            if user_name(value) and _issuance_name_key(user_name(value)) != "nan"
        }
        token_to_user_ids: dict[str, list[str]] = {}
        for user_id, value in users_data.items():
            name = user_name(value)
            token_key = _issuance_token_key(name)
            if name and token_key and token_key != "nan":
                token_to_user_ids.setdefault(token_key, []).append(str(user_id))

        def resolve_user_id(employee_name: str) -> str | None:
            exact = name_to_user_id.get(_issuance_name_key(employee_name))
            if exact:
                return exact
            candidates = token_to_user_ids.get(_issuance_token_key(employee_name), [])
            return candidates[0] if len(candidates) == 1 else None

        added_without_telegram: list[str] = []
        timestamp = datetime.now(timezone.utc).isoformat()

        for employee_name, mints_amount, sticks_amount in rows:
            normalized_name = _issuance_name_key(employee_name)
            user_id = resolve_user_id(employee_name)
            if not user_id:
                user_id = f"excel_{normalized_name.replace(' ', '_')}"
                suffix = 2
                while user_id in users_data and _issuance_name_key(user_name(users_data[user_id])) != normalized_name:
                    user_id = f"excel_{normalized_name.replace(' ', '_')}_{suffix}"
                    suffix += 1
                users_data.setdefault(user_id, make_user_record(employee_name))
                name_to_user_id[normalized_name] = user_id
                token_to_user_ids.setdefault(_issuance_token_key(employee_name), []).append(user_id)
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
        groups_data = staged.get("groups_data", {})
        audit = staged.get("user_audit", {})
        if int(audit.get("after_count", 0)) < int(audit.get("before_count", 0)):
            raise ImportSafetyError("KPI import would reduce registered users")
        current_users = await self.users.load()
        if len(current_users) < int(audit.get("before_count", len(current_users))):
            raise ImportSafetyError("registered users changed after preview")

        def persist(files: dict[str, dict[str, Any]]) -> None:
            files[self.kpi.path].update(kpi_data)
            for employee_id, record in users_data.items():
                files[self.users.path].setdefault(employee_id, record)
            if self.groups is not None:
                files[self.groups.path].update(groups_data)

        paths = [self.kpi.path, self.users.path]
        if self.groups is not None:
            paths.append(self.groups.path)
        await transaction(paths).run(persist)
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


__all__ = ["ImportSafetyError", "ImportService", "build_user_import_audit"]
