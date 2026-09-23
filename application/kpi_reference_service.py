"""Validation and persistence helpers for the monthly KPI reference workbook."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from config import KPI_REFERENCE_FILE
from repositories.json_repository import JsonRepository


class KpiReferenceValidationError(ValueError):
    """Raised when a monthly KPI reference workbook is invalid."""


@dataclass(frozen=True)
class KpiReferenceItem:
    name: str
    weight_percent: float
    quantity: float
    threshold_percent: float | None


def _number(value: Any, *, field: str, row_number: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise KpiReferenceValidationError(f"строка {row_number}: {field} должен быть числом") from None
    if number != number or number in (float("inf"), float("-inf")):
        raise KpiReferenceValidationError(f"строка {row_number}: {field} должен быть конечным числом")
    return number


def build_kpi_reference(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise KpiReferenceValidationError("Excel не содержит заполненных KPI")
    items: list[dict[str, Any]] = []
    names: set[str] = set()
    total_weight = 0.0
    for row_number, row in enumerate(rows, start=2):
        name = str(row.get("name", "")).strip()
        if not name or name.casefold() in {"nan", "none"}:
            continue
        key = " ".join(name.casefold().split())
        if key in names:
            raise KpiReferenceValidationError(f"строка {row_number}: KPI «{name}» указан повторно")
        names.add(key)
        weight = _number(row.get("weight_percent"), field="процентный вес", row_number=row_number)
        quantity = _number(row.get("quantity"), field="количество", row_number=row_number)
        threshold_raw = row.get("threshold_percent")
        threshold = None
        is_nan = False
        try:
            is_nan = math.isnan(float(threshold_raw)) if threshold_raw is not None else False
        except (TypeError, ValueError):
            is_nan = False
        if (
            threshold_raw is not None
            and not is_nan
            and str(threshold_raw).strip().casefold() not in {"", "nan", "none"}
        ):
            threshold = _number(threshold_raw, field="threshold", row_number=row_number)
        if weight < 0 or weight > 100:
            raise KpiReferenceValidationError(f"строка {row_number}: вес должен быть от 0 до 100%")
        if quantity < 0:
            raise KpiReferenceValidationError(f"строка {row_number}: количество не может быть отрицательным")
        if threshold is not None and (threshold < 0 or threshold > 100):
            raise KpiReferenceValidationError(f"строка {row_number}: threshold должен быть от 0 до 100%")
        total_weight += weight
        items.append(
            {
                "name": name,
                "weight_percent": weight,
                "quantity": quantity,
                **({"threshold_percent": threshold} if threshold is not None else {}),
            }
        )
    if not items:
        raise KpiReferenceValidationError("Excel не содержит заполненных KPI")
    difference = total_weight - 100.0
    if abs(difference) > 0.01:
        if difference < 0:
            correction = f"не хватает {abs(difference):.2f} процентных пунктов"
        else:
            correction = f"лишние {difference:.2f} процентных пунктов"
        raise KpiReferenceValidationError(
            "Сумма весов KPI должна быть ровно 100%. "
            f"Сейчас: {total_weight:.2f}%. {correction}. "
            "Исправьте веса в Excel и загрузите файл повторно."
        )
    return {
        "schema_version": 1,
        "effective_month": datetime.now().strftime("%Y-%m"),
        "updated_at": datetime.now().isoformat(),
        "total_weight_percent": total_weight,
        "items": items,
    }



def _metric_key(value: Any) -> str:
    text = str(value or "").strip().casefold().replace("ё", "е")
    return " ".join(text.replace("-", " ").replace("_", " ").split())


REFERENCE_ALIASES = {
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


def resolve_kpi_reference(reference: dict[str, Any] | None) -> dict[str, float] | None:
    """Resolve handbook rows into canonical plan fields and KPI weights.

    GT and Re-trafic map directly. Microacts may be a combined row or separate
    LAS/LAU rows; their quantities and weights are combined into Microacts.
    A three-row handbook with renamed labels keeps the historical positional
    order GT, Microacts, Re-trafic.
    """
    if not isinstance(reference, dict) or not isinstance(reference.get("items"), list):
        return None

    items = [item for item in reference["items"] if isinstance(item, dict)]
    plans = {"gt_plan": 0.0, "micro_plan": 0.0, "retrafic_plan": 0.0}
    weights = {"gt": 0.0, "microacts": 0.0, "retrafic": 0.0}
    mapped = False
    explicit_microacts = False
    separate_micro_plan = 0.0
    separate_micro_weight = 0.0

    for item in items:
        name = _metric_key(item.get("name"))
        try:
            quantity = float(item.get("quantity", 0) or 0)
            weight = float(item.get("weight_percent", 0) or 0) / 100.0
        except (TypeError, ValueError):
            continue
        matched = next((metric for metric, names in REFERENCE_ALIASES.items() if name in names), None)
        if matched == "gt":
            plans["gt_plan"] += quantity
            weights["gt"] += weight
            mapped = True
        elif matched == "retrafic":
            plans["retrafic_plan"] += quantity
            weights["retrafic"] += weight
            mapped = True
        elif matched == "microacts":
            plans["micro_plan"] += quantity
            weights["microacts"] += weight
            explicit_microacts = True
            mapped = True
        elif matched in {"las", "lau"}:
            separate_micro_plan += quantity
            separate_micro_weight += weight
            mapped = True

    if not explicit_microacts:
        plans["micro_plan"] = separate_micro_plan
        weights["microacts"] = separate_micro_weight

    if mapped:
        return {**plans, **weights}

    if len(items) == 3:
        for plan_key, weight_key, item in zip(
            ("gt_plan", "micro_plan", "retrafic_plan"),
            ("gt", "microacts", "retrafic"),
            items,
            strict=True,
        ):
            try:
                plans[plan_key] = float(item.get("quantity", 0) or 0)
                weights[weight_key] = float(item.get("weight_percent", 0) or 0) / 100.0
            except (TypeError, ValueError):
                return None
        return {**plans, **weights}
    return None


def resolve_kpi_reference_plans(reference: dict[str, Any] | None) -> dict[str, float] | None:
    """Return only canonical monthly plan values from the KPI handbook."""
    resolved = resolve_kpi_reference(reference)
    if not resolved:
        return None
    return {key: resolved[key] for key in ("gt_plan", "micro_plan", "retrafic_plan")}


def resolve_kpi_reference_weights(reference: dict[str, Any] | None) -> dict[str, float] | None:
    """Return only canonical fractional KPI weights from the KPI handbook."""
    resolved = resolve_kpi_reference(reference)
    if not resolved:
        return None
    return {key: resolved[key] for key in ("gt", "microacts", "retrafic")}


async def save_kpi_reference(reference: dict[str, Any]) -> None:
    def replace(data: dict[str, Any]) -> None:
        data.clear()
        data.update(reference)

    await JsonRepository(KPI_REFERENCE_FILE).update(replace)


async def load_kpi_reference() -> dict[str, Any]:
    data = await JsonRepository(KPI_REFERENCE_FILE).load()
    return data if isinstance(data, dict) else {}


__all__ = ["KpiReferenceValidationError", "build_kpi_reference", "load_kpi_reference", "save_kpi_reference", "resolve_kpi_reference", "resolve_kpi_reference_plans", "resolve_kpi_reference_weights"]
