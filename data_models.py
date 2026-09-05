"""Canonical JSON record models with backward-compatible readers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any, fallback: str = "") -> str:
    return str(value if value is not None else fallback).strip()


def user_name(record: Any, fallback: str = "") -> str:
    if isinstance(record, dict):
        return _text(record.get("name") or record.get("full_name"), fallback)
    return _text(record, fallback)


def make_user_record(name: str, *, created_at: str | None = None, updated_at: str | None = None) -> dict[str, Any]:
    now = updated_at or utc_now()
    return {
        "schema_version": SCHEMA_VERSION,
        "name": _text(name),
        "created_at": created_at or now,
        "updated_at": now,
    }


def group_name(record: Any, fallback: str | None = None) -> str | None:
    value = record.get("group") or record.get("team") if isinstance(record, dict) else record
    text = _text(value)
    return text or fallback


def make_group_record(name: str, group: str, *, updated_at: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "name": _text(name),
        "group": _text(group),
        "updated_at": updated_at or utc_now(),
    }


def registration_request(record: Any, *, user_id: str | int | None = None) -> dict[str, Any]:
    source = dict(record) if isinstance(record, dict) else {"name": _text(record)}
    result = {
        "schema_version": int(source.get("schema_version", SCHEMA_VERSION)),
        "kind": "registration",
        "name": user_name(source, _text(user_id, "Пользователь")),
        "group": _text(source.get("group") or source.get("team"), ""),
        "created_at": _text(source.get("created_at"), utc_now() if isinstance(record, dict) else ""),
    }
    return result


def team_request(record: Any, *, user_id: str | int | None = None) -> dict[str, Any]:
    source = dict(record) if isinstance(record, dict) else {}
    return {
        "schema_version": int(source.get("schema_version", SCHEMA_VERSION)),
        "kind": "team",
        "name": user_name(source, _text(user_id, "Пользователь")),
        "team": _text(source.get("team") or source.get("group"), ""),
        "created_at": _text(source.get("created_at"), utc_now()),
    }


def user_request(record: Any, *, user_id: str | int | None = None) -> dict[str, Any]:
    source = dict(record) if isinstance(record, dict) else {"text": _text(record)}
    return {
        "schema_version": int(source.get("schema_version", SCHEMA_VERSION)),
        "kind": "user",
        "user_id": _text(source.get("user_id"), _text(user_id)),
        "name": user_name(source, "Пользователь"),
        "text": _text(source.get("text")),
        "created_at": _text(source.get("created_at"), utc_now()),
    }


def make_team_record(name: str, team: str, *, updated_at: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "name": _text(name),
        "team": _text(team),
        "updated_at": updated_at or utc_now(),
    }


def make_issuance_record(
    name: str,
    *,
    mints_issued: float = 0.0,
    sticks_issued: float = 0.0,
    mints_used_baseline: float = 0.0,
    sticks_used_baseline: float = 0.0,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "name": _text(name),
        "mints_issued": float(mints_issued),
        "sticks_issued": float(sticks_issued),
        "mints_used_baseline": float(mints_used_baseline),
        "sticks_used_baseline": float(sticks_used_baseline),
        "history": list(history or []),
    }


def normalize_issuance_record(record: Any, *, name: str = "") -> dict[str, Any]:
    source = dict(record) if isinstance(record, dict) else {}
    return make_issuance_record(
        user_name(source, name),
        mints_issued=float(source.get("mints_issued", 0) or 0),
        sticks_issued=float(source.get("sticks_issued", 0) or 0),
        mints_used_baseline=float(source.get("mints_used_baseline", 0) or 0),
        sticks_used_baseline=float(source.get("sticks_used_baseline", 0) or 0),
        history=source.get("history") if isinstance(source.get("history"), list) else [],
    )
