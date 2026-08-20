"""Read-only employee report use cases."""
from __future__ import annotations

from dataclasses import dataclass

from config import GROUPS_FILE, ISSUANCE_FILE, KPI_FILE, USERS_FILE
from organization import merge_employee_issuance, normalize_employee_name
from repositories.json_repository import JsonRepository
from services import calculate_balances


@dataclass
class ReportService:
    users: JsonRepository
    groups: JsonRepository
    kpi: JsonRepository
    issuance: JsonRepository

    @classmethod
    def from_default_storage(cls) -> "ReportService":
        return cls(
            users=JsonRepository(USERS_FILE),
            groups=JsonRepository(GROUPS_FILE),
            kpi=JsonRepository(KPI_FILE),
            issuance=JsonRepository(ISSUANCE_FILE),
        )

    async def personal_report(self, employee: dict) -> dict:
        kpi_data, issuance_data = await _gather(self.kpi.load(), self.issuance.load())
        kpi_record = _find_kpi_record(kpi_data, employee)
        merged_issuance = merge_employee_issuance(employee, issuance_data)
        return {
            "employee": employee,
            "kpi": kpi_record,
            "issuance": merged_issuance,
            "balances": calculate_balances(kpi_record, merged_issuance),
        }


def _find_kpi_record(kpi_data: dict, employee: dict) -> dict:
    aliases = {normalize_employee_name(employee.get("name"))}
    aliases.update(normalize_employee_name(alias) for alias in employee.get("aliases", []))
    for key, raw_record in kpi_data.items():
        if not isinstance(raw_record, dict):
            continue
        candidate = raw_record.get("original_name", key)
        if normalize_employee_name(candidate) in aliases:
            return raw_record
    return {}


async def _gather(*coroutines):
    import asyncio

    return await asyncio.gather(*coroutines)


__all__ = ["ReportService"]
