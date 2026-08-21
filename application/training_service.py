"""Application service for employee training delivery history."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from config import BOT_TIMEZONE, TRAINING_HISTORY_FILE
from domain.models import OperationResult
from repositories.json_repository import JsonRepository

TRAINING_ONE = "one"
TRAINING_TWO = "two"
TRAINING_TYPES = (TRAINING_ONE, TRAINING_TWO)


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

    @staticmethod
    def missing_types_from_data(
        data: dict,
        user_id: int | str,
        month: str | None = None,
    ) -> tuple[str, ...]:
        selected_month = month or TrainingService.current_month()
        record = data.get(str(user_id), {})
        deliveries = record.get("deliveries", []) if isinstance(record, dict) else []
        sent_types = {
            str(delivery.get("type"))
            for delivery in deliveries
            if isinstance(delivery, dict) and delivery.get("month") == selected_month
        }
        return tuple(training_type for training_type in TRAINING_TYPES if training_type not in sent_types)

    @staticmethod
    def latest_file_id_from_data(data: dict, user_id: int | str, training_type: str) -> str | None:
        record = data.get(str(user_id), {})
        if not isinstance(record, dict):
            return None
        deliveries = record.get("deliveries", [])
        if not isinstance(deliveries, list):
            return None
        for delivery in reversed(deliveries):
            if not isinstance(delivery, dict) or delivery.get("type") != training_type:
                continue
            file_id = str(delivery.get("file_id", "")).strip()
            if file_id:
                return file_id
        return None

    async def has_sent_this_month(self, user_id: int | str, training_type: str, month: str | None = None) -> bool:
        data = await self.history.load()
        return training_type not in self.missing_types_from_data(data, user_id, month)

    async def missing_types(self, user_id: int | str, month: str | None = None) -> tuple[str, ...]:
        data = await self.history.load()
        return self.missing_types_from_data(data, user_id, month)

    async def record_delivery(
        self,
        user_id: int | str,
        user_name: str,
        training_type: str,
        sender_id: int | str,
        month: str | None = None,
        file_id: str | None = None,
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
            if training_type not in self.missing_types_from_data({target_id: record}, target_id, selected_month):
                already_sent_code = f"training_{training_type}_already_sent"
                return OperationResult(False, already_sent_code, already_sent_code)
            delivery = {
                "type": training_type,
                "month": selected_month,
                "sent_at": datetime.now(ZoneInfo(BOT_TIMEZONE)).isoformat(),
                "sender_id": str(sender_id),
            }
            if file_id:
                delivery["file_id"] = str(file_id)
            deliveries.append(delivery)
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
