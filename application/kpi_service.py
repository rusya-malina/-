"""Application use cases for manual KPI editing and default plans."""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from config import BOT_TIMEZONE, KPI_FILE, PLANS_FILE
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
WORKING_WEEKDAYS = frozenset({3, 4, 5, 6})  # Thursday through Sunday
PLAN_TARGETS = (1.0, 1.11)
LAS_THRESHOLD = 0.40
DEFAULT_TIMEZONE = BOT_TIMEZONE


def clean_name(name: str) -> str:
    return str(name).strip().lower()


def _nonnegative(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def remaining_workdays(as_of: date, period_end: date) -> int:
    """Count working days from today through period end, inclusive."""
    if as_of > period_end:
        return 0
    total = 0
    current = as_of
    while current <= period_end:
        if current.weekday() in WORKING_WEEKDAYS:
            total += 1
        current += timedelta(days=1)
    return total


def _ceil_nonnegative(value: float) -> int:
    return max(0, int(value + 0.999999999))


def build_plan_projection(
    record: dict[str, Any],
    as_of: date | None = None,
    hours_per_workday: int = 4,
) -> dict[str, Any]:
    """Build hourly GT and separate LAS/LAU targets for 100% and 111%.

    The source workbook stores one combined microacts plan. For the plan card,
    that target is split into the existing LAS threshold (40%) and the
    complementary LAU share (60%). Facts remain independent, and the total in
    each row is the sum of the remaining LAS and LAU quantities.
    """
    if hours_per_workday <= 0:
        raise ValueError("hours_per_workday must be positive")
    current_date = as_of or datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).date()
    period_end = date(
        current_date.year,
        current_date.month,
        calendar.monthrange(current_date.year, current_date.month)[1],
    )
    workdays_left = remaining_workdays(current_date, period_end)
    hours_left = workdays_left * hours_per_workday
    gt_fact = float(record.get("gt_fact", 0) or 0)
    las_fact = float(record.get("micro_las_fact", 0) or 0)
    lau_fact = float(record.get("micro_lau_fact", 0) or 0)
    rows: list[dict[str, Any]] = []
    for multiplier in PLAN_TARGETS:
        gt_target = float(record.get("gt_plan", 0) or 0) * multiplier
        micro_total_target = float(record.get("micro_plan", 0) or 0) * multiplier
        las_target = micro_total_target * LAS_THRESHOLD
        lau_target = micro_total_target - las_target
        gt_remaining = max(0.0, gt_target - gt_fact)
        las_remaining = max(0.0, las_target - las_fact)
        lau_remaining = max(0.0, lau_target - lau_fact)
        micro_total_remaining = las_remaining + lau_remaining
        rows.append(
            {
                "target_percent": int(multiplier * 100),
                "gt_target": gt_target,
                "gt_remaining": gt_remaining,
                "gt_per_hour": gt_remaining / hours_left if hours_left else 0.0,
                "gt_per_hour_rounded": _ceil_nonnegative(gt_remaining / hours_left) if hours_left else 0,
                "las_target": las_target,
                "las_remaining": las_remaining,
                "las_per_hour": las_remaining / hours_left if hours_left else 0.0,
                "las_per_hour_rounded": _ceil_nonnegative(las_remaining / hours_left) if hours_left else 0,
                "lau_target": lau_target,
                "lau_remaining": lau_remaining,
                "lau_per_hour": lau_remaining / hours_left if hours_left else 0.0,
                "lau_per_hour_rounded": _ceil_nonnegative(lau_remaining / hours_left) if hours_left else 0,
                "micro_total_target": micro_total_target,
                "micro_total_remaining": micro_total_remaining,
            }
        )
    return {
        "as_of": current_date.isoformat(),
        "period_end": period_end.isoformat(),
        "workdays_left": workdays_left,
        "hours_per_workday": hours_per_workday,
        "hours_left": hours_left,
        "working_weekdays": sorted(WORKING_WEEKDAYS),
        "rows": rows,
    }


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

    async def delete_entry(self, name: str) -> OperationResult:
        key = clean_name(name)

        def remove(data: dict[str, Any]) -> OperationResult:
            if key not in data:
                return OperationResult(False, "not_found", "kpi_entry_not_found", (key,))
            data.pop(key, None)
            return OperationResult(True, "deleted", "kpi_entry_deleted", (key,), {"name": name})

        return await self.kpi.update(remove)

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


__all__ = [
    "DEFAULT_TIMEZONE",
    "KPI_FIELDS",
    "LAS_THRESHOLD",
    "PLAN_FIELDS",
    "KpiService",
    "build_plan_projection",
    "clean_name",
    "remaining_workdays",
]
