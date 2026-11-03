"""Administrative employee management use cases."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from config import (
    DELETED_USERS_FILE,
    GROUPS_FILE,
    ISSUANCE_FILE,
    KPI_ARCHIVE_FILE,
    KPI_FILE,
    OFFHOURS_VISITS_FILE,
    PENDING_FILE,
    REGISTRATION_DRAFTS_FILE,
    TEAM_REQUESTS_FILE,
    TEAMS_FILE,
    TRAINING_HISTORY_FILE,
    USER_REQUESTS_FILE,
    USERS_FILE,
    WORK_STATUS_FILE,
)
from data_models import user_name
from domain.models import OperationResult
from repositories.json_repository import JsonRepository, transaction


@dataclass
class EmployeeAdminService:
    users: JsonRepository
    kpi: JsonRepository
    groups: JsonRepository | None = None
    issuance: JsonRepository | None = None
    deleted: JsonRepository | None = None
    kpi_archive: JsonRepository | None = None
    training: JsonRepository | None = None
    visits: JsonRepository | None = None
    work_status: JsonRepository | None = None
    drafts: JsonRepository | None = None
    pending: JsonRepository | None = None
    user_requests: JsonRepository | None = None
    team_requests: JsonRepository | None = None
    teams: JsonRepository | None = None

    @classmethod
    def from_default_storage(cls) -> "EmployeeAdminService":
        return cls(
            users=JsonRepository(USERS_FILE),
            kpi=JsonRepository(KPI_FILE),
            groups=JsonRepository(GROUPS_FILE),
            issuance=JsonRepository(ISSUANCE_FILE),
            deleted=JsonRepository(DELETED_USERS_FILE),
            kpi_archive=JsonRepository(KPI_ARCHIVE_FILE),
            training=JsonRepository(TRAINING_HISTORY_FILE),
            visits=JsonRepository(OFFHOURS_VISITS_FILE),
            work_status=JsonRepository(WORK_STATUS_FILE),
            drafts=JsonRepository(REGISTRATION_DRAFTS_FILE),
            pending=JsonRepository(PENDING_FILE),
            user_requests=JsonRepository(USER_REQUESTS_FILE),
            team_requests=JsonRepository(TEAM_REQUESTS_FILE),
            teams=JsonRepository(TEAMS_FILE),
        )

    async def delete_registered(self, employee_id: int | str, actor_id: int) -> OperationResult:
        from config import ADMIN_ID

        if str(actor_id) != str(ADMIN_ID):
            return OperationResult(False, "forbidden", "permission_denied")

        employee_id = str(employee_id)
        clean_name: str | None = None
        removed_aliases: list[str] = []

        paths = [self.users.path, self.kpi.path]
        optional_repositories = (
            self.groups,
            self.issuance,
            self.deleted,
            self.kpi_archive,
            self.training,
            self.visits,
            self.work_status,
            self.drafts,
            self.pending,
            self.user_requests,
            self.team_requests,
            self.teams,
        )
        paths.extend(repository.path for repository in optional_repositories if repository is not None)

        def mutate(files: dict[str, dict[str, Any]]) -> OperationResult:
            nonlocal clean_name
            raw_user = files[self.users.path].get(employee_id)
            if raw_user is None:
                return OperationResult(False, "not_found", "registered_user_not_found")

            clean_name = _normalize_name(user_name(raw_user, employee_id))
            aliases = {employee_id}
            for path in (self.users.path, self.groups.path if self.groups is not None else None):
                if path is None:
                    continue
                for key, record in files[path].items():
                    if _normalize_name(user_name(record, key)) == clean_name:
                        aliases.add(str(key))
            removed_aliases.extend(sorted(aliases - {employee_id}))
            files[self.users.path].pop(employee_id, None)

            for key, record in list(files[self.kpi.path].items()):
                record_name = record.get("original_name", key) if isinstance(record, dict) else key
                if _normalize_name(record_name) == clean_name:
                    files[self.kpi.path].pop(key, None)

            if self.groups is not None:
                for key, record in list(files[self.groups.path].items()):
                    if key == employee_id or _normalize_name(user_name(record, key)) == clean_name:
                        files[self.groups.path].pop(key, None)

            if self.issuance is not None:
                for key, record in list(files[self.issuance.path].items()):
                    if key == "_schema_version":
                        continue
                    if key == employee_id or _normalize_name(user_name(record, key)) == clean_name:
                        files[self.issuance.path].pop(key, None)

            if self.deleted is not None:
                for key, record in list(files[self.deleted.path].items()):
                    if str(key) in aliases or (
                        isinstance(record, dict) and _normalize_name(record.get("name")) == clean_name
                    ):
                        files[self.deleted.path].pop(key, None)

            if self.kpi_archive is not None:
                archive = files[self.kpi_archive.path]
                records = archive.get("records", {}) if isinstance(archive, dict) else {}
                if isinstance(records, dict):
                    for key, record in list(records.items()):
                        employee = record.get("employee", {}) if isinstance(record, dict) else {}
                        kpi = record.get("kpi", {}) if isinstance(record, dict) else {}
                        original_name = kpi.get("original_name") if isinstance(kpi, dict) else None
                        if (
                            _record_matches_person(employee, aliases, clean_name)
                            or _normalize_name(original_name) == clean_name
                        ):
                            records.pop(key, None)

            if self.training is not None:
                for key, record in list(files[self.training.path].items()):
                    if str(key) in aliases or _record_matches_person(record, aliases, clean_name):
                        files[self.training.path].pop(key, None)

            if self.visits is not None:
                visits = files[self.visits.path]
                bookings = visits.get("bookings", {})
                if isinstance(bookings, dict):
                    visits["bookings"] = {
                        key: record
                        for key, record in bookings.items()
                        if not _record_matches_person(record, aliases, clean_name)
                    }
                history = visits.get("history", [])
                if isinstance(history, list):
                    visits["history"] = [
                        record for record in history if not _record_matches_person(record, aliases, clean_name)
                    ]

            if self.work_status is not None:
                _remove_from_work_status(files[self.work_status.path], aliases, clean_name)

            for repository in (self.drafts, self.pending, self.user_requests, self.team_requests):
                if repository is not None:
                    _remove_personal_request(files[repository.path], aliases, clean_name)
            if self.teams is not None:
                for key, record in list(files[self.teams.path].items()):
                    if str(key) in aliases or _record_matches_person(record, aliases, clean_name):
                        files[self.teams.path].pop(key, None)

            return OperationResult(
                True,
                "deleted",
                "registered_user_deleted",
                (employee_id,),
                {
                    "name": clean_name or "",
                    "removed_aliases": removed_aliases,
                    "identity_archived": False,
                },
            )

        return await transaction(paths).run(mutate)


def _normalize_name(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _record_matches_person(record: object, aliases: set[str], clean_name: str) -> bool:
    if not isinstance(record, dict):
        return False
    for key in ("user_id", "telegram_id", "sender_id", "receiver_id"):
        if str(record.get(key, "")) in aliases:
            return True
    return any(_normalize_name(record.get(key)) == clean_name for key in ("name", "sender_name", "receiver_name"))


def _remove_from_work_status(data: dict[str, Any], aliases: set[str], clean_name: str) -> None:
    for day in data.values():
        if not isinstance(day, dict):
            continue
        employees = day.get("employees", {})
        if isinstance(employees, dict):
            for key, record in list(employees.items()):
                if str(key) in aliases or _record_matches_person(record, aliases, clean_name):
                    employees.pop(key, None)
        invites = day.get("invites", {})
        if isinstance(invites, dict):
            for key, record in list(invites.items()):
                if _record_matches_person(record, aliases, clean_name):
                    invites.pop(key, None)


def _remove_personal_request(data: dict[str, Any], aliases: set[str], clean_name: str) -> None:
    for key, record in list(data.items()):
        if str(key) in aliases or _record_matches_person(record, aliases, clean_name):
            data.pop(key, None)


__all__ = ["EmployeeAdminService"]
