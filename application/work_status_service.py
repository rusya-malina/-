""" "Application service for daily work status and pair invitations."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from config import BOT_TIMEZONE, GROUPS_FILE, USERS_FILE, WORK_STATUS_FILE
from organization import TEAM_GROUPS, build_employee_registry
from storage import load_json, update_json

STATUS_FILE = WORK_STATUS_FILE


def _today() -> str:
    return datetime.now(ZoneInfo(BOT_TIMEZONE)).date().isoformat()


async def _roster() -> list[dict[str, Any]]:
    users = await load_json(USERS_FILE)
    groups = await load_json(GROUPS_FILE)
    return [
        item
        for item in build_employee_registry(users, groups)
        if item.get("group") in TEAM_GROUPS and str(item.get("user_id", "")).isdigit()
    ]


async def _load_day() -> dict[str, Any]:
    data = await load_json(STATUS_FILE)
    day = data.get(_today(), {})
    if not isinstance(day, dict):
        day = {}
    day.setdefault("employees", {})
    day.setdefault("invites", {})
    return day


async def get_today_status(user_id: str) -> dict[str, Any]:
    day = await _load_day()
    return dict(day["employees"].get(str(user_id), {}))


def _employee_name(roster: list[dict[str, Any]], user_id: str) -> str:
    return next((item["name"] for item in roster if str(user_id) in item.get("aliases", [])), "Сотрудник")


def _employee_group(roster: list[dict[str, Any]], user_id: str) -> str | None:
    return next((item.get("group") for item in roster if str(user_id) in item.get("aliases", [])), None)


async def set_work_status(user_id: str, status: str) -> dict[str, Any]:
    user_id = str(user_id)
    roster = await _roster()
    employee = next((item for item in roster if user_id in item.get("aliases", [])), None)
    if employee is None:
        return {"ok": False, "message": "⚠️ Сотрудник не найден в команде A/R."}

    day_key = _today()

    def mutate(data: dict[str, Any]) -> None:
        day = data.setdefault(day_key, {"employees": {}, "invites": {}})
        employees = day.setdefault("employees", {})
        record = employees.setdefault(user_id, {})
        record.update(
            {
                "user_id": user_id,
                "name": employee["name"],
                "group": employee.get("group"),
                "status": status,
                "updated_at": datetime.now(ZoneInfo(BOT_TIMEZONE)).isoformat(),
            }
        )
        if status == "not_working":
            pair_id = record.pop("pair_user_id", None)
            record.pop("pair_name", None)
            for invite in day.setdefault("invites", {}).values():
                if invite.get("status") == "pending" and (
                    str(invite.get("sender_id")) == user_id or str(invite.get("receiver_id")) == user_id
                ):
                    invite["status"] = "cancelled"
                    invite["cancelled_at"] = datetime.now(ZoneInfo(BOT_TIMEZONE)).isoformat()
            if pair_id:
                partner = employees.get(str(pair_id))
                if isinstance(partner, dict):
                    partner.pop("pair_user_id", None)
                    partner.pop("pair_name", None)
                    partner["status"] = "working"
        else:
            # A repeated "working" action must not break an already confirmed pair.
            # The pair is explicitly released only when the employee switches to
            # "not_working".
            pass

    await update_json(STATUS_FILE, mutate)
    return {"ok": True, "status": status}


async def get_pair_candidates(user_id: str) -> list[dict[str, Any]]:
    user_id = str(user_id)
    roster = await _roster()
    day = await _load_day()
    own = day["employees"].get(user_id, {})
    group = _employee_group(roster, user_id)
    if own.get("status") != "working" or own.get("pair_user_id"):
        return []

    pending_targets = {
        str(invite.get("receiver_id"))
        for invite in day["invites"].values()
        if invite.get("status") == "pending" and str(invite.get("sender_id")) == user_id
    }
    candidates = []
    for employee in roster:
        target_id = str(employee["user_id"])
        if target_id == user_id or employee.get("group") != group:
            continue
        target = day["employees"].get(target_id, {})
        if target.get("status") != "working" or target.get("pair_user_id"):
            continue
        if target_id in pending_targets:
            continue
        candidates.append({"user_id": target_id, "name": employee["name"], "group": group})
    return candidates


async def create_pair_invite(sender_id: str, receiver_id: str) -> dict[str, Any]:
    sender_id, receiver_id = str(sender_id), str(receiver_id)
    roster = await _roster()
    day = await _load_day()
    sender = day["employees"].get(sender_id, {})
    receiver = day["employees"].get(receiver_id, {})
    sender_employee = next((x for x in roster if sender_id in x.get("aliases", [])), None)
    receiver_employee = next((x for x in roster if receiver_id in x.get("aliases", [])), None)

    if not sender_employee or not receiver_employee:
        return {"ok": False, "message": "⚠️ Сотрудник не найден."}
    if sender_employee.get("group") != receiver_employee.get("group"):
        return {"ok": False, "message": "⚠️ В пару можно выбрать только коллегу из своей команды."}
    if sender.get("status") != "working" or sender.get("pair_user_id"):
        return {"ok": False, "message": "⚠️ Сначала отметьте «Работаю» и убедитесь, что вы не в паре."}
    if receiver.get("status") != "working" or receiver.get("pair_user_id"):
        return {"ok": False, "message": "⚠️ Коллега уже не доступна для пары."}

    for invite in day["invites"].values():
        if invite.get("status") == "pending" and (
            str(invite.get("sender_id")) == receiver_id and str(invite.get("receiver_id")) == sender_id
        ):
            return {"ok": False, "message": "ℹ️ У коллеги уже есть приглашение вам."}

    invite_id = f"{sender_id}:{receiver_id}:{_today()}"

    def mutate(data: dict[str, Any]) -> None:
        current = data.setdefault(_today(), {"employees": {}, "invites": {}})
        current.setdefault("invites", {})[invite_id] = {
            "invite_id": invite_id,
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "sender_name": sender_employee["name"],
            "receiver_name": receiver_employee["name"],
            "status": "pending",
            "created_at": datetime.now(ZoneInfo(BOT_TIMEZONE)).isoformat(),
        }

    await update_json(STATUS_FILE, mutate)
    return {
        "ok": True,
        "invite_id": invite_id,
        "sender_id": sender_id,
        "sender_name": sender_employee["name"],
        "target_name": receiver_employee["name"],
    }


async def accept_pair_invite(invite_id: str, receiver_id: str) -> dict[str, Any]:
    receiver_id = str(receiver_id)
    day = await _load_day()
    invite = day["invites"].get(invite_id)
    if not invite or invite.get("status") != "pending":
        return {"ok": False, "message": "⚠️ Приглашение уже недействительно."}
    if str(invite.get("receiver_id")) != receiver_id:
        return {"ok": False, "message": "⛔️ Это приглашение адресовано другому сотруднику."}

    sender_id = str(invite["sender_id"])
    if (
        day["employees"].get(sender_id, {}).get("status") != "working"
        or day["employees"].get(receiver_id, {}).get("status") != "working"
    ):
        return {"ok": False, "message": "⚠️ Оба сотрудника должны иметь статус «Работаю»."}
    if day["employees"].get(sender_id, {}).get("pair_user_id") or day["employees"].get(receiver_id, {}).get(
        "pair_user_id"
    ):
        return {"ok": False, "message": "⚠️ Один из сотрудников уже находится в паре."}

    sender_name = invite["sender_name"]
    receiver_name = invite["receiver_name"]

    def mutate(data: dict[str, Any]) -> None:
        current = data[_today()]
        current["invites"][invite_id]["status"] = "accepted"
        current["invites"][invite_id]["accepted_at"] = datetime.now(ZoneInfo(BOT_TIMEZONE)).isoformat()
        current["employees"][sender_id].update({"pair_user_id": receiver_id, "pair_name": receiver_name})
        current["employees"][receiver_id].update({"pair_user_id": sender_id, "pair_name": sender_name})
        for other in current["invites"].values():
            if (
                other.get("status") == "pending"
                and (
                    str(other.get("sender_id")) in {sender_id, receiver_id}
                    or str(other.get("receiver_id")) in {sender_id, receiver_id}
                )
                and other.get("invite_id") != invite_id
            ):
                other["status"] = "cancelled"

    await update_json(STATUS_FILE, mutate)
    return {
        "ok": True,
        "message": f"✅ Вы приняли приглашение *{sender_name}*.\\n👯 Сегодня вы в паре.",
        "sender_id": sender_id,
        "receiver_name": receiver_name,
    }


async def reject_pair_invite(invite_id: str, reason: str = "rejected") -> dict[str, Any]:
    day = await _load_day()
    invite = day["invites"].get(invite_id)
    if not invite or invite.get("status") != "pending":
        return {"ok": False, "message": "⚠️ Приглашение уже недействительно."}
    sender_id = str(invite["sender_id"])
    receiver_id = str(invite["receiver_id"])

    def mutate(data: dict[str, Any]) -> None:
        current = data[_today()]
        current["invites"][invite_id]["status"] = "rejected" if reason == "user_rejected" else "cancelled"
        current["invites"][invite_id]["rejected_at"] = datetime.now(ZoneInfo(BOT_TIMEZONE)).isoformat()

    await update_json(STATUS_FILE, mutate)
    return {
        "ok": True,
        "message": "❌ Приглашение отклонено.",
        "sender_id": sender_id,
        "receiver_id": receiver_id,
        "receiver_name": invite.get("receiver_name", "Коллега"),
    }


async def get_coordinator_overview() -> dict[str, Any]:
    roster = await _roster()
    day = await _load_day()
    employees = day["employees"]
    pairs = []
    seen = set()
    working = []
    not_working = []
    for employee in roster:
        user_id = str(employee["user_id"])
        record = employees.get(user_id, {})
        status = record.get("status")
        pair_id = record.get("pair_user_id")
        if pair_id:
            key = tuple(sorted((user_id, str(pair_id))))
            if key not in seen:
                seen.add(key)
                pairs.append(
                    {
                        "first_name": record.get("name", employee["name"]),
                        "second_name": record.get("pair_name", "Коллега"),
                        "first_group": record.get("group", employee.get("group")),
                    }
                )
        elif status == "working":
            working.append({"name": employee["name"], "group": employee.get("group")})
        else:
            not_working.append({"name": employee["name"], "group": employee.get("group")})

    return {
        "date": _today(),
        "pairs": pairs,
        "working": working,
        "not_working": not_working,
    }
