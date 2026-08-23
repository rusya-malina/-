from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from config import BOT_TIMEZONE, PLANS_FILE
from repositories.json_repository import JsonRepository
from storage import load_json_sync, save_json_sync

MONTHLY_KPI_KEY = "monthly_kpi"
MONTHLY_KPI_SCHEMA_VERSION = 1


class MonthlyKpiValidationError(ValueError):
    """Raised when a monthly KPI directory is invalid."""


def _normalize_name(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _metric_key(name: str, index: int) -> str:
    normalized = re.sub(r"[^a-zа-яё0-9]+", "_", _normalize_name(name)).strip("_")
    return normalized or f"metric_{index}"


def _current_period() -> str:
    return datetime.now(ZoneInfo(BOT_TIMEZONE)).strftime("%Y-%m")


def _next_period(period: str | None = None) -> str:
    value = period or _current_period()
    year, month = (int(part) for part in value.split("-"))
    if month == 12:
        return f"{year + 1:04d}-01"
    return f"{year:04d}-{month + 1:02d}"


def _period_at_or_before(left: str, right: str) -> bool:
    return left <= right


class MonthlyKpiService:
    def __init__(self, repository: JsonRepository):
        self.repository = repository

    @classmethod
    def from_default_storage(cls) -> "MonthlyKpiService":
        return cls(JsonRepository(PLANS_FILE))

    @staticmethod
    def prepare(rows: list[dict[str, Any]]) -> dict[str, Any]:
        metrics: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, row in enumerate(rows, start=1):
            name = str(row.get("name") or row.get("kpi") or row.get("full_name") or "").strip()
            if not name or _normalize_name(name) in {"nan", "none"}:
                continue
            try:
                plan = float(row.get("plan"))
                weight = float(row.get("weight"))
            except (TypeError, ValueError) as error:
                raise MonthlyKpiValidationError(f"Строка {index}: план и вес должны быть числами") from error
            if plan < 0:
                raise MonthlyKpiValidationError(f"Строка {index}: план не может быть отрицательным")
            if weight < 0:
                raise MonthlyKpiValidationError(f"Строка {index}: вес не может быть отрицательным")
            normalized = _normalize_name(name)
            if normalized in seen:
                raise MonthlyKpiValidationError(f"Дубликат KPI: {name}")
            seen.add(normalized)
            metrics.append(
                {
                    "key": _metric_key(name, index),
                    "name": name,
                    "plan": plan,
                    "weight": weight,
                }
            )

        if not metrics:
            raise MonthlyKpiValidationError("В Excel не найдено ни одного KPI")
        total_weight = sum(metric["weight"] for metric in metrics)
        if abs(total_weight - 100.0) > 0.01:
            raise MonthlyKpiValidationError(f"Сумма весов должна быть 100%, сейчас: {total_weight:g}%")
        return {
            "schema_version": MONTHLY_KPI_SCHEMA_VERSION,
            "metrics": metrics,
            "row_count": len(metrics),
            "total_weight": total_weight,
        }

    async def get_active(self) -> dict[str, Any] | None:
        data = await self.repository.load()
        monthly = data.get(MONTHLY_KPI_KEY)
        return monthly.get("active") if isinstance(monthly, dict) and isinstance(monthly.get("active"), dict) else None

    async def activate_now(self, prepared: dict[str, Any], period: str | None = None) -> dict[str, Any]:
        selected_period = period or _current_period()

        def mutate(data: dict[str, Any]) -> dict[str, Any]:
            monthly = data.get(MONTHLY_KPI_KEY)
            if not isinstance(monthly, dict):
                monthly = {"schema_version": MONTHLY_KPI_SCHEMA_VERSION, "history": []}
            active = {
                "period": selected_period,
                "activated_at": datetime.now().astimezone().isoformat(),
                "metrics": prepared["metrics"],
                "total_weight": prepared["total_weight"],
            }
            history = monthly.get("history", [])
            if not isinstance(history, list):
                history = []
            if isinstance(monthly.get("active"), dict):
                history.append(monthly["active"])
            monthly.update({"schema_version": MONTHLY_KPI_SCHEMA_VERSION, "active": active, "pending": None, "history": history})
            data[MONTHLY_KPI_KEY] = monthly
            return active

        return await self.repository.update(mutate)

    async def schedule_next(self, prepared: dict[str, Any], period: str | None = None) -> dict[str, Any]:
        activation_period = period or _next_period()

        def mutate(data: dict[str, Any]) -> dict[str, Any]:
            monthly = data.get(MONTHLY_KPI_KEY)
            if not isinstance(monthly, dict):
                monthly = {"schema_version": MONTHLY_KPI_SCHEMA_VERSION, "history": []}
            pending = {
                "period": activation_period,
                "created_at": datetime.now().astimezone().isoformat(),
                "metrics": prepared["metrics"],
                "total_weight": prepared["total_weight"],
            }
            monthly.update({"schema_version": MONTHLY_KPI_SCHEMA_VERSION, "pending": pending})
            data[MONTHLY_KPI_KEY] = monthly
            return pending

        return await self.repository.update(mutate)

    @staticmethod
    def apply_due_sync(period: str | None = None) -> bool:
        selected_period = period or _current_period()
        data = load_json_sync(PLANS_FILE)
        monthly = data.get(MONTHLY_KPI_KEY)
        if not isinstance(monthly, dict) or not isinstance(monthly.get("pending"), dict):
            return False
        pending = monthly["pending"]
        activation_period = str(pending.get("period") or "")
        if not activation_period or not _period_at_or_before(activation_period, selected_period):
            return False
        history = monthly.get("history", [])
        if not isinstance(history, list):
            history = []
        if isinstance(monthly.get("active"), dict):
            history.append(monthly["active"])
        monthly["active"] = {
            "period": activation_period,
            "activated_at": datetime.now().astimezone().isoformat(),
            "metrics": pending.get("metrics", []),
            "total_weight": pending.get("total_weight", 0),
        }
        monthly["pending"] = None
        monthly["history"] = history
        monthly["schema_version"] = MONTHLY_KPI_SCHEMA_VERSION
        data[MONTHLY_KPI_KEY] = monthly
        save_json_sync(data, PLANS_FILE)
        try:
            from github_sync import sync_data_state_sync

            sync_data_state_sync((PLANS_FILE,))
        except (ImportError, OSError, RuntimeError):
            pass
        return True


__all__ = ["MONTHLY_KPI_KEY", "MonthlyKpiService", "MonthlyKpiValidationError"]
