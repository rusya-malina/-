"""Derived KPI calculations for the A/R LAMP management hierarchy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from config import BOT_TIMEZONE, GROUPS_FILE, KPI_FILE, KPI_REFERENCE_FILE, TEAM_KPI_FILE, USERS_FILE
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


def _metric_key(value: Any) -> str:
    text = str(value or "").strip().casefold().replace("ё", "е")
    return " ".join(text.replace("-", " ").replace("_", " ").split())


def _reference_weights(reference: dict[str, Any] | None) -> dict[str, float] | None:
    """Map handbook KPI names to report metrics and return fractional weights.

    The workbook may use either one combined microacts row or separate LAS and
    LAU rows. In the latter case their weights are combined for the existing
    aggregate ``microacts`` metric. Unknown handbook names are intentionally
    ignored; when no supported metric can be mapped, the report is marked as
    not configured instead of silently falling back to stale 40/40/20 values.
    """
    if not isinstance(reference, dict) or not isinstance(reference.get("items"), list):
        return None

    aliases = {
        "gt": {"gt", "гт", "gross traffic", "трафик"},
        "microacts": {
            "microacts",
            "micro acts",
            "микроакты",
            "микро акты",
            "микроакты общие",
            "microacts total",
        },
        "las": {"las", "лас"},
        "lau": {"lau", "лау"},
        "retrafic": {"retrafic", "re trafic", "re traffic", "ре трафик", "ретрафик"},
    }
    items = [item for item in reference["items"] if isinstance(item, dict)]
    weights = {"gt": 0.0, "microacts": 0.0, "retrafic": 0.0}
    mapped = False
    explicit_microacts = False
    separate_microacts = 0.0
    for item in items:
        name = _metric_key(item.get("name"))
        try:
            weight = float(item.get("weight_percent", 0) or 0) / 100.0
        except (TypeError, ValueError):
            continue
        if weight < 0:
            continue
        matched = next((metric for metric, names in aliases.items() if name in names), None)
        if matched in {"gt", "retrafic"}:
            weights[matched] += weight
            mapped = True
        elif matched == "microacts":
            weights["microacts"] += weight
            explicit_microacts = True
            mapped = True
        elif matched in {"las", "lau"}:
            separate_microacts += weight
            mapped = True
    if not explicit_microacts:
        weights["microacts"] = separate_microacts
    if mapped:
        return weights
    if len(items) == 3:
        # The monthly handbook has historically used this canonical order.
        # It keeps renamed display labels connected to the source KPI fields.
        positional = {"gt": 0.0, "microacts": 0.0, "retrafic": 0.0}
        for metric, item in zip(positional, items, strict=True):
            try:
                positional[metric] = float(item.get("weight_percent", 0) or 0) / 100.0
            except (TypeError, ValueError):
                return {}
        return positional
    return {}


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
    work_time_fact = totals["field_hours"]
    work_time_total_fact = totals["office_hours"] + totals["field_hours"]
    work_time_plan = len(records) * 64.0
    metrics = {
        "work_time": {
            **_metric(work_time_plan, work_time_fact),
            "office_hours": totals["office_hours"],
            "field_hours": totals["field_hours"],
            "total_fact": work_time_total_fact,
            "execution_basis": "field_hours",
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
    weights: dict[str, float] | None = DEFAULT_WEIGHTS,
    weights_source: str = "legacy_default",
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
        "overall": {**_overall(metrics, weights), "weights_source": weights_source},
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
    kpi_reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic monthly team KPI snapshot from employee KPI data."""
    now = datetime.now(ZoneInfo(BOT_TIMEZONE))
    selected_period = period or now.strftime("%Y-%m")
    timestamp = calculated_at or now.isoformat()
    reference_weights = _reference_weights(kpi_reference)
    weights = reference_weights if reference_weights else (None if kpi_reference is not None else DEFAULT_WEIGHTS)
    weights_source = (
        "kpi_reference"
        if reference_weights
        else ("kpi_reference_unmapped" if kpi_reference is not None else "legacy_default")
    )
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
            weights=weights,
            weights_source=weights_source,
        )
        for group in SOURCE_GROUPS
    }
    manager_reports: dict[str, Any] = {}
    for manager_group, scope in MANAGER_SCOPES.items():
        manager_employees = [employee for employee in source_records if employee.get("group") in scope]
        report = _report(
            manager_employees,
            scope_groups=scope,
            manager_group=manager_group,
            weights=weights,
            weights_source=weights_source,
        )
        report["team_keys"] = list(scope)
        report["by_team"] = {team: teams[team] for team in scope}
        manager_reports[manager_group] = report

    return {
        "period": selected_period,
        "schema_version": SCHEMA_VERSION,
        "calculation_version": CALCULATION_VERSION,
        "kpi_reference_updated_at": (kpi_reference.get("updated_at") if isinstance(kpi_reference, dict) else None),
        "calculated_at": timestamp,
        "source_import_id": source_import_id,
        "source_groups": list(SOURCE_GROUPS),
        "weights": weights,
        "weights_source": weights_source,
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
    kpi_reference: JsonRepository

    @classmethod
    def from_default_storage(cls) -> "TeamKpiService":
        return cls(
            team_kpi=JsonRepository(TEAM_KPI_FILE),
            users=JsonRepository(USERS_FILE),
            groups=JsonRepository(GROUPS_FILE),
            kpi=JsonRepository(KPI_FILE),
            kpi_reference=JsonRepository(KPI_REFERENCE_FILE),
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
        kpi_reference = await self.kpi_reference.load()
        snapshot = build_team_kpi_snapshot(
            users,
            groups,
            kpi_data,
            period=period,
            source_import_id=source_import_id,
            kpi_reference=kpi_reference if kpi_reference else None,
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
