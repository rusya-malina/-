"""Validation and persistence helpers for the monthly KPI reference workbook."""
from __future__ import annotations

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
        if threshold_raw is not None and str(threshold_raw).strip().casefold() not in {"", "nan", "none"}:
            threshold = _number(threshold_raw, field="threshold", row_number=row_number)
        if weight < 0 or weight > 100:
            raise KpiReferenceValidationError(f"строка {row_number}: вес должен быть от 0 до 100%")
        if quantity < 0:
            raise KpiReferenceValidationError(f"строка {row_number}: количество не может быть отрицательным")
        if threshold is not None and (threshold < 0 or threshold > 100):
            raise KpiReferenceValidationError(f"строка {row_number}: threshold должен быть от 0 до 100%")
        total_weight += weight
        items.append({
            "name": name,
            "weight_percent": weight,
            "quantity": quantity,
            **({"threshold_percent": threshold} if threshold is not None else {}),
        })
    if not items:
        raise KpiReferenceValidationError("Excel не содержит заполненных KPI")
    if abs(total_weight - 100.0) > 0.01:
        raise KpiReferenceValidationError(
            f"сумма весов должна быть равна 100%, сейчас {total_weight:.2f}%"
        )
    return {
        "schema_version": 1,
        "effective_month": datetime.now().strftime("%Y-%m"),
        "updated_at": datetime.now().isoformat(),
        "total_weight_percent": total_weight,
        "items": items,
    }


async def save_kpi_reference(reference: dict[str, Any]) -> None:
    def replace(data: dict[str, Any]) -> None:
        data.clear()
        data.update(reference)

    await JsonRepository(KPI_REFERENCE_FILE).update(replace)


async def load_kpi_reference() -> dict[str, Any]:
    data = await JsonRepository(KPI_REFERENCE_FILE).load()
    return data if isinstance(data, dict) else {}


__all__ = ["KpiReferenceValidationError", "build_kpi_reference", "load_kpi_reference", "save_kpi_reference"]
