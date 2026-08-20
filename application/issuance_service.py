"""Application use cases for MINTS and sticks issuance."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from config import ISSUANCE_FILE
from data_models import normalize_issuance_record
from domain.models import OperationResult
from repositories.json_repository import JsonRepository

ISSUANCE_FIELDS = {"mints": "mints_issued", "sticks": "sticks_issued"}


@dataclass
class IssuanceService:
    """Owns issuance mutation and immutable operation history."""

    issuance: JsonRepository

    @classmethod
    def from_default_storage(cls) -> "IssuanceService":
        return cls(issuance=JsonRepository(ISSUANCE_FILE))

    async def issue(
        self,
        user_id: int | str,
        user_name: str,
        issuance_type: str,
        amount: Any,
        admin_id: int | str,
    ) -> OperationResult:
        key = str(user_id)
        name = str(user_name).strip()
        field = ISSUANCE_FIELDS.get(str(issuance_type))
        try:
            numeric_amount = float(str(amount).replace(",", ".").strip())
        except (TypeError, ValueError):
            numeric_amount = math.nan
        if not key or not name or field is None or not math.isfinite(numeric_amount) or numeric_amount <= 0:
            return OperationResult(False, "invalid_input", "invalid_issuance")

        record: dict[str, Any] = {}

        def mutate(data: dict[str, Any]) -> None:
            nonlocal record
            record = normalize_issuance_record(data.get(key), name=name)
            record[field] += numeric_amount
            record["history"].append(
                {
                    "type": str(issuance_type),
                    "amount": numeric_amount,
                    "admin_id": str(admin_id),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            data[key] = record

        await self.issuance.update(mutate)
        return OperationResult(
            True,
            "issued",
            "issuance_saved",
            (key,),
            {"name": name, "issuance_type": str(issuance_type), "amount": numeric_amount, "total": record[field]},
        )


__all__ = ["ISSUANCE_FIELDS", "IssuanceService"]
