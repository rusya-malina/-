"""Application service for employee training delivery history."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from config import BOT_TIMEZONE, TRAINING_HISTORY_FILE
from domain.models import OperationResult
from repositories.json_repository import JsonRepository

TRAINING_ONE = "one"
TRAINING_TWO = "two"
TRAINING_TYPES = frozenset({TRAINING_ONE, TRAINING_TWO})


class TrainingService:
    """Owns the persistent monthly delivery guard for employee training."""

    def __init__(self, history: JsonRepository):
        self.history = history

    @classmethod
    def from_default_storage(cls) -> "TrainingService":
        return cls(history=JsonRepository(TRAINING_HISTORY_FILE))

    @staticmethod
    def current_month() -> str:
        return datetime.now(ZoneInfo(BOT_TIMEZONE)).strftime("%Y-%m")

    async def has_sent_this_month(self, user_id: int | str, training_type: str, month: str | None = None) -> bool:
        target_id = str(user_id)
        selected_month = month or self.current_month()
        data = await self.history.load()
        record = data.get(target_id, {})
        if not isinstance(record, dict):
            return False
        return any(
            isinstance(delivery, dict)
            and delivery.get("type") == training_type
            and delivery.get("month") == selected_month
            for delivery in record.get("deliveries", [])
        )

    async def record_delivery(
        self,
        user_id: int | str,
        user_name: str,
        training_type: str,
        sender_id: int | str,
        month: str | None = None,
    ) -> OperationResult:
        target_id = str(user_id)
        name = str(user_name).strip()
        selected_month = month or self.current_month()
        if not target_id.isdigit() or not name or training_type not in TRAINING_TYPES:
            return OperationResult(False, "invalid_training", "invalid_training")

        def mutate(data: dict) -> OperationResult:
            record = data.get(target_id)
            if not isinstance(record, dict):
                record = {"schema_version": 1, "name": name, "deliveries": []}
            deliveries = record.get("deliveries")
            if not isinstance(deliveries, list):
                deliveries = []
            if training_type == TRAINING_ONE and any(
                isinstance(delivery, dict)
                and delivery.get("type") == TRAINING_ONE
                and delivery.get("month") == selected_month
                for delivery in deliveries
            ):
                return OperationResult(False, "training_one_already_sent", "training_one_already_sent")
            deliveries.append(
                {
                    "type": training_type,
                    "month": selected_month,
                    "sent_at": datetime.now(ZoneInfo(BOT_TIMEZONE)).isoformat(),
                    "sender_id": str(sender_id),
                }
            )
            record.update({"schema_version": 1, "name": name, "deliveries": deliveries})
            data[target_id] = record
            return OperationResult(
                True,
                "training_recorded",
                "training_recorded",
                (target_id,),
                {"training_type": training_type, "month": selected_month},
            )

        return await self.history.update(mutate)


__all__ = ["TRAINING_ONE", "TRAINING_TWO", "TRAINING_TYPES", "TrainingService"]
