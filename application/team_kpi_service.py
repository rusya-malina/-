"""Derived KPI calculations for the A/R LAMP management hierarchy."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from config import BOT_TIMEZONE, GROUPS_FILE, KPI_FILE, TEAM_KPI_FILE, USERS_FILE
from organization import build_employee_registry
from repositories.json_repository import JsonRepository

SOURCE_GROUPS = ("A LAMP", "R LAMP")
MANAGER_SCOPES = {
    "coor A": ("A LAMP",),
    "coor R": ("R LAMP",),
    "SPV": SOURCE_GROUPS,
    "MNG": SOURCE_GROUPS,
}
DEFAULT_WEIGHTS = {"gt": 0.4, "microacts": 0.4, "retrafic": 0.2}
SCHEMA_VERSION = 1
CALCULATION_VERSION = "weighted_v2_with_work_hours"


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _percent(fact: float, plan: float) -> float:
    return (fact / plan * 100) if plan > 0 else 0.0


def _metric(plan: float, fact: float) -> dict[str, float]:
    return {"plan": plan, "fact": fact, "percent": _percent(fact, plan)}


def _aggregate_metrics(records: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str], list[str]]:
    totals = {
        "gt_plan": 0.0,
        "gt_fact": 0.0,
        "micro_plan": 0.0,
        "micro_las_fact": 0.0,
        "micro_lau_fact": 0.0,
        "retrafic_plan": 0.0,
        "retrafic_fact": 0.0,
        "office_hours": 0.0,
        "field_hours": 0.0,
    }
    missing_employee_ids: list[str] = []
    zero_plan_metrics: set[str] = set()

    for employee in records:
        kpi = employee.get("kpi")
        if not isinstance(kpi, dict):
            missing_employee_ids.append(str(employee["user_id"]))
            continue
        for field in totals:
            totals[field] += _number(kpi.get(field))

    micro_fact = totals["micro_las_fact"] + totals["micro_lau_fact"]
    las_percent = _percent(totals["micro_las_fact"], micro_fact)
    work_time_fact = totals["office_hours"] + totals["field_hours"]
    work_time_plan = len(records) * 64.0
    metrics = {
        "work_time": {
            **_metric(work_time_plan, work_time_fact),
            "office_hours": totals["office_hours"],
            "field_hours": totals["field_hours"],
            "hours_per_employee": 64.0,
            "employee_count": len(records),
        },
        "gt": _metric(totals["gt_plan"], totals["gt_fact"]),
        "microacts": {
            **_metric(totals["micro_plan"], micro_fact),
            "las_fact": totals["micro_las_fact"],
            "lau_fact": totals["micro_lau_fact"],
            "las_percent": las_percent,
            "las_threshold_percent": 40.0,
            "las_threshold_status": "no_data" if micro_fact <= 0 else ("pass" if las_percent >= 40 else "below"),
        },
        "retrafic": _metric(totals["retrafic_plan"], totals["retrafic_fact"]),
    }
    for metric_name, plan in (
        ("gt", totals["gt_plan"]),
        ("microacts", totals["micro_plan"]),
        ("retrafic", totals["retrafic_plan"]),
    ):
        if plan <= 0:
            zero_plan_metrics.add(metric_name)

    warnings = []
    if missing_employee_ids:
        warnings.append("У части сотрудников отсутствуют KPI-данные")
    if zero_plan_metrics:
        warnings.append("Для части показателей план равен нулю")

    return metrics, sorted(missing_employee_ids), sorted(zero_plan_metrics) + warnings


def _overall(metrics: dict[str, Any], weights: dict[str, float] | None = DEFAULT_WEIGHTS) -> dict[str, Any]:
    if not weights:
        return {"percent": None, "status": "not_configured", "weights": None}
    percent = sum(metrics[name]["percent"] * weight for name, weight in weights.items())
    return {"percent": percent, "status": "calculated", "weights": dict(weights)}


def _report(
    employees: list[dict[str, Any]],
    *,
    scope_groups: tuple[str, ...],
    manager_group: str | None = None,
    team_group: str | None = None,
) -> dict[str, Any]:
    metrics, missing_ids, quality_tail = _aggregate_metrics(employees)
    zero_plan_metrics = [item for item in quality_tail if item in {"gt", "microacts", "retrafic"}]
    warnings = [item for item in quality_tail if item not in {"gt", "microacts", "retrafic"}]
    return {
        "manager_group": manager_group,
        "team_group": team_group,
        "scope_groups": list(scope_groups),
        "employee_ids": sorted(str(item["user_id"]) for item in employees),
        "employee_count": len(employees),
        "metrics": metrics,
        "overall": _overall(metrics),
        "quality": {
            "missing_employee_ids": missing_ids,
            "zero_plan_metrics": zero_plan_metrics,
            "duplicate_names": [],
            "warnings": warnings,
        },
    }


def build_team_kpi_snapshot(
    users: dict[str, Any],
    groups: dict[str, Any],
    kpi_data: dict[str, Any],
    *,
    period: str | None = None,
    source_import_id: str | None = None,
    calculated_at: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic monthly team KPI snapshot from employee KPI data."""
    now = datetime.now(ZoneInfo(BOT_TIMEZONE))
    selected_period = period or now.strftime("%Y-%m")
    timestamp = calculated_at or now.isoformat()
    registry = build_employee_registry(users, groups, kpi_data, {})
    source_records: list[dict[str, Any]] = []
    for employee in registry:
        group = employee.get("group")
        if group not in SOURCE_GROUPS:
            continue
        source_records.append(
            {
                **employee,
                "kpi": kpi_data.get(employee.get("name_key", "")),
            }
        )

    teams = {
        group: _report(
            [employee for employee in source_records if employee.get("group") == group],
            scope_groups=(group,),
            team_group=group,
        )
        for group in SOURCE_GROUPS
    }
    manager_reports: dict[str, Any] = {}
    for manager_group, scope in MANAGER_SCOPES.items():
        manager_employees = [employee for employee in source_records if employee.get("group") in scope]
        report = _report(manager_employees, scope_groups=scope, manager_group=manager_group)
        report["team_keys"] = list(scope)
        report["by_team"] = {
            team: teams[team]
            for team in scope
        }
        manager_reports[manager_group] = report

    return {
        "period": selected_period,
        "schema_version": SCHEMA_VERSION,
        "calculation_version": CALCULATION_VERSION,
        "calculated_at": timestamp,
        "source_import_id": source_import_id,
        "source_groups": list(SOURCE_GROUPS),
        "teams": teams,
        "manager_reports": manager_reports,
    }


@dataclass
class TeamKpiService:
    """Persists derived team KPI snapshots without replacing source KPI data."""

    team_kpi: JsonRepository
    users: JsonRepository
    groups: JsonRepository
    kpi: JsonRepository

    @classmethod
    def from_default_storage(cls) -> "TeamKpiService":
        return cls(
            team_kpi=JsonRepository(TEAM_KPI_FILE),
            users=JsonRepository(USERS_FILE),
            groups=JsonRepository(GROUPS_FILE),
            kpi=JsonRepository(KPI_FILE),
        )

    async def rebuild(
        self,
        *,
        period: str | None = None,
        source_import_id: str | None = None,
    ) -> dict[str, Any]:
        users = await self.users.load()
        groups = await self.groups.load()
        kpi_data = await self.kpi.load()
        snapshot = build_team_kpi_snapshot(
            users,
            groups,
            kpi_data,
            period=period,
            source_import_id=source_import_id,
        )
        selected_period = snapshot["period"]
        calculated_at = snapshot["calculated_at"]

        def persist(data: dict[str, Any]) -> None:
            data["schema_version"] = SCHEMA_VERSION
            data["calculation_version"] = CALCULATION_VERSION
            data["current_period"] = selected_period
            data["updated_at"] = calculated_at
            periods = data.setdefault("periods", {})
            periods[selected_period] = snapshot

        await self.team_kpi.update(persist)
        return snapshot

    async def load_current(self, period: str | None = None) -> dict[str, Any] | None:
        data = await self.team_kpi.load()
        selected_period = period or data.get("current_period")
        if not selected_period:
            return None
        snapshot = data.get("periods", {}).get(selected_period)
        return dict(snapshot) if isinstance(snapshot, dict) else None


__all__ = ["TeamKpiService", "build_team_kpi_snapshot"]
