"""Registration use cases independent from Telegram presentation."""
from __future__ import annotations

import re
from dataclasses import dataclass

from config import GROUPS_FILE, ISSUANCE_FILE, PENDING_FILE, USERS_FILE
from data_models import make_group_record, make_user_record, registration_request, user_name
from domain.models import OperationResult
from repositories.json_repository import JsonRepository, transaction


@dataclass
class RegistrationService:
    pending: JsonRepository
    users: JsonRepository
    groups: JsonRepository
    issuance: JsonRepository | None = None

    @classmethod
    def from_default_storage(cls) -> "RegistrationService":
        return cls(
            pending=JsonRepository(PENDING_FILE),
            users=JsonRepository(USERS_FILE),
            groups=JsonRepository(GROUPS_FILE),
            issuance=JsonRepository(ISSUANCE_FILE),
        )

    async def approve(self, request_id: int | str, actor_id: int) -> OperationResult:
        return await self._process(request_id, actor_id, accepted=True)

    async def reject(self, request_id: int | str, actor_id: int) -> OperationResult:
        return await self._process(request_id, actor_id, accepted=False)

    async def _process(self, request_id: int | str, actor_id: int, accepted: bool) -> OperationResult:
        if str(actor_id) != self._admin_id():
            return OperationResult(False, "forbidden", "permission_denied")

        user_id = str(request_id)

        def mutate(files: dict[str, dict]) -> OperationResult:
            removed_request = files[self.pending.path].pop(user_id, None)
            if removed_request is None:
                return OperationResult(False, "not_found", "registration_not_found")

            request = registration_request(removed_request, user_id=user_id)
            name = user_name(request, "Пользователь")
            group = request.get("group") or ""
            migrated_aliases: list[str] = []
            if accepted:
                normalized_name = _normalize_name(name)
                for legacy_id, legacy_record in list(files[self.users.path].items()):
                    legacy_name = user_name(legacy_record)
                    if str(legacy_id).startswith("excel_") and _normalize_name(legacy_name) == normalized_name:
                        migrated_aliases.append(str(legacy_id))
                        files[self.users.path].pop(legacy_id, None)
                        files[self.groups.path].pop(legacy_id, None)
                        if self.issuance is not None:
                            legacy_issuance = files[self.issuance.path].pop(legacy_id, None)
                            if legacy_issuance is not None and user_id not in files[self.issuance.path]:
                                files[self.issuance.path][user_id] = legacy_issuance
                files[self.users.path][user_id] = make_user_record(name)
                files[self.groups.path][user_id] = make_group_record(name, group)
                code = "accepted"
                message_key = "registration_accepted"
            else:
                files[self.groups.path].pop(user_id, None)
                code = "rejected"
                message_key = "registration_rejected"
            return OperationResult(
                True,
                code,
                message_key,
                (user_id,),
                {"name": name, "group": group, "migrated_aliases": migrated_aliases},
            )

        paths = (self.pending.path, self.users.path, self.groups.path)
        if self.issuance is not None:
            paths += (self.issuance.path,)
        return await transaction(paths).run(mutate)

    @staticmethod
    def _admin_id() -> str:
        from config import ADMIN_ID

        return str(ADMIN_ID)


def _normalize_name(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


__all__ = ["RegistrationService"]
