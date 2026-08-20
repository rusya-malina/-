"""Группы пользователей и черновики регистрации."""
from bot_context import (
    GROUPS_FILE,
    REGISTRATION_DRAFTS_FILE,
    TEAM_OPTIONS,
    datetime,
    timezone,
)
from storage import load_json, load_json_sync, update_json


def normalize_group(group: str | None) -> str | None:
    value = str(group or "").strip()
    return value if value in TEAM_OPTIONS else None


def get_group_from_record(record: object) -> str | None:
    if isinstance(record, dict):
        return normalize_group(record.get("group") or record.get("team"))
    return normalize_group(record if isinstance(record, str) else None)


async def get_user_group(user_id: int | str) -> str | None:
    groups = await load_json(GROUPS_FILE)
    return get_group_from_record(groups.get(str(user_id)))


def get_user_group_sync(user_id: int | str) -> str | None:
    groups = load_json_sync(GROUPS_FILE)
    return get_group_from_record(groups.get(str(user_id)))


async def save_user_group(user_id: int | str, name: str, group: str) -> None:
    normalized = normalize_group(group)
    if not normalized:
        raise ValueError(f"Неизвестная группа: {group}")

    def mutate(groups: dict) -> None:
        groups[str(user_id)] = {
            "name": name,
            "group": normalized,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    await update_json(GROUPS_FILE, mutate)


async def remove_user_group(user_id: int | str) -> None:
    def mutate(groups: dict) -> None:
        groups.pop(str(user_id), None)

    await update_json(GROUPS_FILE, mutate)


async def get_registration_draft(user_id: int | str) -> dict | None:
    drafts = await load_json(REGISTRATION_DRAFTS_FILE)
    draft = drafts.get(str(user_id))
    return dict(draft) if isinstance(draft, dict) else None


async def save_registration_draft(user_id: int | str, name: str) -> None:
    def mutate(drafts: dict) -> None:
        drafts[str(user_id)] = {
            "name": name,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    await update_json(REGISTRATION_DRAFTS_FILE, mutate)


async def remove_registration_draft(user_id: int | str) -> None:
    def mutate(drafts: dict) -> None:
        drafts.pop(str(user_id), None)

    await update_json(REGISTRATION_DRAFTS_FILE, mutate)
