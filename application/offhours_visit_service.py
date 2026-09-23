"""Booking rules for off-hours venue visits."""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from config import BOT_TIMEZONE, OFFHOURS_VISITS_FILE
from domain.models import OperationResult
from repositories.json_repository import JsonRepository

VENUES = {
    "bla_bla_bar": "Bla Bla Bar",
    "kuranty": "Куранты",
    "spletni": "Сплетни",
    "zebra_hype": "Зебра (Hype)",
    "q_bar": "Q bar",
    "john_dilinger": "John Dilinger",
    "midnight": "Midnight",
    "zevon": "Зевон (суб)",
    "shanghai": "Шанхай",
    "gao_gao": "Гао Гао",
}
ALLOWED_WEEKDAYS = frozenset({3, 4, 5, 6})  # Thursday through Sunday
VENUE_WEEKDAYS = {"zevon": frozenset({5})}  # Зевон работает только по субботам
MAX_EMPLOYEES_PER_VENUE_DAY = 2
MAX_USER_VENUE_MONTHLY_BOOKINGS = 2


def local_today() -> date:
    return datetime.now(ZoneInfo(BOT_TIMEZONE)).date()


def week_visit_dates(as_of: date | None = None) -> tuple[date, ...]:
    """Return Thursday-Sunday for the calendar week containing *as_of*."""
    current = as_of or local_today()
    monday = current - timedelta(days=current.weekday())
    return tuple(monday + timedelta(days=offset) for offset in range(3, 7))


def allowed_weekdays_for_venue(venue: str | None = None) -> frozenset[int]:
    return VENUE_WEEKDAYS.get(str(venue), ALLOWED_WEEKDAYS)


def month_visit_dates(as_of: date | None = None, venue: str | None = None) -> tuple[date, ...]:
    """Return available dates for a venue in the current calendar month."""
    current = as_of or local_today()
    last_day = monthrange(current.year, current.month)[1]
    allowed_weekdays = allowed_weekdays_for_venue(venue)
    return tuple(
        day
        for number in range(1, last_day + 1)
        if (day := date(current.year, current.month, number)).weekday() in allowed_weekdays
    )


def _empty_store() -> dict[str, Any]:
    return {"schema_version": 1, "bookings": {}, "history": []}


def _ensure_store(data: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data.setdefault("schema_version", 1)
    bookings = data.setdefault("bookings", {})
    history = data.setdefault("history", [])
    if not isinstance(bookings, dict):
        bookings = {}
        data["bookings"] = bookings
    if not isinstance(history, list):
        history = []
        data["history"] = history
    return bookings, history


def _active_records(data: dict[str, Any]) -> list[dict[str, Any]]:
    bookings, _ = _ensure_store(data)
    return [record for record in bookings.values() if isinstance(record, dict) and record.get("status") == "active"]


@dataclass
class OffhoursVisitService:
    visits: JsonRepository

    @classmethod
    def from_default_storage(cls) -> "OffhoursVisitService":
        return cls(visits=JsonRepository(OFFHOURS_VISITS_FILE))

    async def book(
        self,
        user_id: int | str,
        name: str,
        group: str,
        venue: str,
        visit_date: str,
    ) -> OperationResult:
        user_key = str(user_id)
        person_name = str(name).strip()
        group_name = str(group).strip()
        try:
            parsed_date = date.fromisoformat(str(visit_date))
        except ValueError:
            return OperationResult(False, "invalid_date", "invalid_visit_date")
        today = local_today()
        if (
            not user_key
            or not person_name
            or group_name not in {"A LAMP", "R LAMP"}
            or venue not in VENUES
            or parsed_date.weekday() not in allowed_weekdays_for_venue(venue)
            or parsed_date < today
            or parsed_date.year != today.year
            or parsed_date.month != today.month
        ):
            return OperationResult(False, "invalid_input", "invalid_visit_booking")

        booking_id = uuid4().hex
        now = datetime.now(timezone.utc).isoformat()

        def mutate(data: dict[str, Any]) -> OperationResult:
            bookings, history = _ensure_store(data)
            active = _active_records(data)
            same_day = [
                record
                for record in active
                if str(record.get("user_id")) == user_key and record.get("visit_date") == parsed_date.isoformat()
            ]
            if same_day:
                existing = same_day[0]
                return OperationResult(
                    False,
                    "user_day_conflict",
                    "offhours_user_day_conflict",
                    details={
                        "venue": existing.get("venue"),
                        "venue_name": VENUES.get(str(existing.get("venue")), str(existing.get("venue", ""))),
                        "visit_date": parsed_date.isoformat(),
                    },
                )

            monthly_venue_bookings = [
                record
                for record in active
                if (
                    str(record.get("user_id")) == user_key
                    and record.get("venue") == venue
                    and str(record.get("visit_date", ""))[:7] == parsed_date.isoformat()[:7]
                )
            ]
            if len(monthly_venue_bookings) >= MAX_USER_VENUE_MONTHLY_BOOKINGS:
                return OperationResult(
                    False,
                    "user_venue_month_full",
                    "offhours_user_venue_month_full",
                    details={
                        "venue": venue,
                        "venue_name": VENUES[venue],
                        "month": parsed_date.strftime("%m.%Y"),
                        "bookings": len(monthly_venue_bookings),
                    },
                )

            venue_day = [
                record
                for record in active
                if record.get("venue") == venue and record.get("visit_date") == parsed_date.isoformat()
            ]
            if len(venue_day) >= MAX_EMPLOYEES_PER_VENUE_DAY:
                return OperationResult(
                    False,
                    "venue_full",
                    "offhours_venue_full",
                    details={"venue": venue, "visit_date": parsed_date.isoformat()},
                )

            record = {
                "booking_id": booking_id,
                "user_id": user_key,
                "name": person_name,
                "group": group_name,
                "venue": venue,
                "visit_date": parsed_date.isoformat(),
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
            bookings[booking_id] = record
            history.append(
                {
                    "action": "booked",
                    "booking_id": booking_id,
                    "user_id": user_key,
                    "venue": venue,
                    "visit_date": parsed_date.isoformat(),
                    "created_at": now,
                }
            )
            return OperationResult(
                True,
                "booked",
                "offhours_booking_saved",
                (booking_id,),
                {"booking": dict(record), "occupied": len(venue_day) + 1},
            )

        return await self.visits.update(mutate)

    async def cancel(self, user_id: int | str, booking_id: str) -> OperationResult:
        user_key = str(user_id)
        now = datetime.now(timezone.utc).isoformat()

        def mutate(data: dict[str, Any]) -> OperationResult:
            bookings, history = _ensure_store(data)
            record = bookings.get(str(booking_id))
            if not isinstance(record, dict) or record.get("status") != "active":
                return OperationResult(False, "not_found", "offhours_booking_not_found")
            if str(record.get("user_id")) != user_key:
                return OperationResult(False, "forbidden", "offhours_booking_forbidden")
            record["status"] = "cancelled"
            record["updated_at"] = now
            record["cancelled_at"] = now
            history.append(
                {
                    "action": "cancelled",
                    "booking_id": str(booking_id),
                    "user_id": user_key,
                    "venue": record.get("venue"),
                    "visit_date": record.get("visit_date"),
                    "created_at": now,
                }
            )
            return OperationResult(
                True,
                "cancelled",
                "offhours_booking_cancelled",
                (str(booking_id),),
                {"booking": dict(record)},
            )

        return await self.visits.update(mutate)

    async def active_bookings(self) -> list[dict[str, Any]]:
        data = await self.visits.load()
        records = [dict(record) for record in _active_records(data)]
        return sorted(
            records, key=lambda item: (str(item.get("visit_date")), str(item.get("venue")), str(item.get("name")))
        )

    async def user_bookings(self, user_id: int | str, *, include_past: bool = False) -> list[dict[str, Any]]:
        user_key = str(user_id)
        today = local_today().isoformat()
        records = [
            record
            for record in await self.active_bookings()
            if str(record.get("user_id")) == user_key and (include_past or str(record.get("visit_date", "")) >= today)
        ]
        return records


__all__ = [
    "ALLOWED_WEEKDAYS",
    "MAX_EMPLOYEES_PER_VENUE_DAY",
    "MAX_USER_VENUE_MONTHLY_BOOKINGS",
    "OffhoursVisitService",
    "allowed_weekdays_for_venue",
    "local_today",
    "month_visit_dates",
    "VENUES",
    "week_visit_dates",
]
