"""Application use cases for manual KPI editing and default plans."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import KPI_FILE, PLANS_FILE
from domain.models import OperationResult
from repositories.json_repository import JsonRepository

KPI_FIELDS = (
    "gt_fact",
    "micro_las_fact",
    "micro_lau_fact",
    "retrafic_fact",
    "office_hours",
    "field_hours",
)
PLAN_FIELDS = ("gt_plan", "micro_plan", "retrafic_plan")


def clean_name(name: str) -> str:
    return str(name).strip().lower()


def _nonnegative(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


@dataclass
class KpiService:
    """Owns KPI record and default-plan mutations without Telegram dependencies."""

    kpi: JsonRepository
    plans: JsonRepository

    @classmethod
    def from_default_storage(cls) -> "KpiService":
        return cls(kpi=JsonRepository(KPI_FILE), plans=JsonRepository(PLANS_FILE))

    async def list_employee_names(self) -> list[str]:
        data = await self.kpi.load()
        return sorted(
            str(record.get("original_name", key))
            for key, record in data.items()
            if isinstance(record, dict)
        )

    async def get_entry(self, name: str) -> dict[str, Any] | None:
        data = await self.kpi.load()
        return data.get(clean_name(name))

    async def set_default_plans(self, values: dict[str, Any]) -> OperationResult:
        plans: dict[str, float] = {}
        for field in PLAN_FIELDS:
            value = _nonnegative(values.get(field))
            if value is None:
                return OperationResult(False, "invalid_value", "invalid_plan", details={"field": field})
            plans[field] = value

        await self.plans.update(lambda data: data.update(plans))
        return OperationResult(True, "updated", "plans_updated", details={"plans": plans})

    async def save_manual_entry(self, name: str, values: dict[str, Any]) -> OperationResult:
        original_name = str(name).strip()
        key = clean_name(original_name)
        if len(original_name) < 3 or len(original_name.split()) < 2 or not key:
            return OperationResult(False, "invalid_name", "invalid_employee_name")

        facts: dict[str, float] = {}
        for field in KPI_FIELDS:
            value = _nonnegative(values.get(field))
            if value is None:
                return OperationResult(False, "invalid_value", "invalid_kpi_value", details={"field": field})
            facts[field] = value

        current_plans = await self.plans.load()
        current_entry = await self.get_entry(original_name) or {}
        record = {
            "original_name": original_name,
            "gt_plan": float(current_entry.get("gt_plan", current_plans.get("gt_plan", 0)) or 0),
            "gt_fact": facts["gt_fact"],
            "micro_plan": float(current_entry.get("micro_plan", current_plans.get("micro_plan", 0)) or 0),
            "micro_las_fact": facts["micro_las_fact"],
            "micro_lau_fact": facts["micro_lau_fact"],
            "retrafic_plan": float(current_entry.get("retrafic_plan", current_plans.get("retrafic_plan", 0)) or 0),
            "retrafic_fact": facts["retrafic_fact"],
            "office_hours": facts["office_hours"],
            "field_hours": facts["field_hours"],
        }
        await self.kpi.update(lambda data: data.__setitem__(key, record))
        return OperationResult(True, "saved", "kpi_saved", (key,), {"name": original_name, "record": record})


__all__ = ["KPI_FIELDS", "PLAN_FIELDS", "KpiService", "clean_name"]
