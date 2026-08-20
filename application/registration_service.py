"""Registration use cases independent from Telegram presentation."""
from __future__ import annotations

from dataclasses import dataclass

from config import GROUPS_FILE, PENDING_FILE, USERS_FILE
from data_models import make_group_record, make_user_record, registration_request, user_name
from domain.models import OperationResult
from repositories.json_repository import JsonRepository, transaction


@dataclass
class RegistrationService:
    pending: JsonRepository
    users: JsonRepository
    groups: JsonRepository

    @classmethod
    def from_default_storage(cls) -> "RegistrationService":
        return cls(
            pending=JsonRepository(PENDING_FILE),
            users=JsonRepository(USERS_FILE),
            groups=JsonRepository(GROUPS_FILE),
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
            if accepted:
                files[self.users.path][user_id] = make_user_record(name)
                files[self.groups.path][user_id] = make_group_record(name, group)
                code = "accepted"
                message_key = "registration_accepted"
            else:
                files[self.groups.path].pop(user_id, None)
                code = "rejected"
                message_key = "registration_rejected"
            return OperationResult(True, code, message_key, (user_id,), {"name": name, "group": group})

        return await transaction((self.pending.path, self.users.path, self.groups.path)).run(mutate)

    @staticmethod
    def _admin_id() -> str:
        from config import ADMIN_ID

        return str(ADMIN_ID)


__all__ = ["RegistrationService"]
