"""Employee use cases built on repositories and the canonical registry."""
from __future__ import annotations

from dataclasses import dataclass

from config import GROUPS_FILE, ISSUANCE_FILE, KPI_FILE, USERS_FILE
from organization import build_employee_registry, get_employee_by_id
from repositories.json_repository import JsonRepository


@dataclass
class EmployeeService:
    users: JsonRepository
    groups: JsonRepository
    kpi: JsonRepository
    issuance: JsonRepository

    @classmethod
    def from_default_storage(cls) -> "EmployeeService":
        return cls(
            users=JsonRepository(USERS_FILE),
            groups=JsonRepository(GROUPS_FILE),
            kpi=JsonRepository(KPI_FILE),
            issuance=JsonRepository(ISSUANCE_FILE),
        )

    async def list_registry(self) -> list[dict]:
        users, groups, kpi, issuance = await _load_documents(self)
        return build_employee_registry(users, groups, kpi, issuance)

    async def find_by_id(self, employee_id: int | str) -> dict | None:
        users, groups, kpi, issuance = await _load_documents(self)
        return get_employee_by_id(employee_id, users, groups, kpi, issuance)


async def _load_documents(service: EmployeeService) -> tuple[dict, dict, dict, dict]:
    return await _gather(
        service.users.load(),
        service.groups.load(),
        service.kpi.load(),
        service.issuance.load(),
    )


async def _gather(*coroutines):
    import asyncio

    return tuple(await asyncio.gather(*coroutines))


__all__ = ["EmployeeService"]
