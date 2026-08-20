"""Application use cases for team selection and moderation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import TEAM_REQUESTS_FILE, TEAMS_FILE
from data_models import make_team_record, team_request, user_name
from domain.models import OperationResult
from repositories.json_repository import JsonRepository, transaction


@dataclass
class TeamService:
    """Owns canonical team requests and moderation mutations."""

    requests: JsonRepository
    teams: JsonRepository

    @classmethod
    def from_default_storage(cls) -> "TeamService":
        return cls(
            requests=JsonRepository(TEAM_REQUESTS_FILE),
            teams=JsonRepository(TEAMS_FILE),
        )

    async def create_request(self, user_id: int | str, name: str, team: str) -> OperationResult:
        key = str(user_id)
        clean_name = str(name).strip()
        clean_team = str(team).strip()
        if not key or not clean_name or not clean_team:
            return OperationResult(False, "invalid_input", "invalid_team_request")
        record = team_request({"user_id": key, "name": clean_name, "team": clean_team}, user_id=key)
        await self.requests.update(lambda data: data.__setitem__(key, record))
        return OperationResult(True, "created", "team_request_created", (key,), {"name": clean_name, "team": clean_team})

    async def get_request(self, user_id: int | str) -> dict[str, Any] | None:
        return (await self.requests.load()).get(str(user_id))

    async def accept_request(self, user_id: int | str) -> OperationResult:
        key = str(user_id)
        result: OperationResult | None = None

        def mutate(files: dict[str, dict[str, Any]]) -> None:
            nonlocal result
            request = files[self.requests.path].get(key)
            if not request:
                result = OperationResult(False, "not_found", "team_request_not_found")
                return
            canonical = team_request(request, user_id=key)
            name = user_name(canonical)
            team = canonical["team"]
            files[self.teams.path][key] = make_team_record(name, team)
            files[self.requests.path].pop(key, None)
            result = OperationResult(True, "accepted", "team_request_accepted", (key,), {"name": name, "team": team})

        await transaction((self.teams.path, self.requests.path)).run(mutate)
        return result or OperationResult(False, "error", "team_request_failed")

    async def reject_request(self, user_id: int | str) -> OperationResult:
        key = str(user_id)
        removed = False

        def mutate(data: dict[str, Any]) -> None:
            nonlocal removed
            removed = data.pop(key, None) is not None

        await self.requests.update(mutate)
        if not removed:
            return OperationResult(False, "not_found", "team_request_not_found")
        return OperationResult(True, "rejected", "team_request_rejected", (key,))


__all__ = ["TeamService"]
