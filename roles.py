"""Группы пользователей и черновики регистрации."""
from bot_context import GROUPS_FILE, REGISTRATION_DRAFTS_FILE, TEAM_OPTIONS, datetime, json, logging, os, timezone
from storage import load_json, save_json


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
    if not os.path.exists(GROUPS_FILE):
        return None
    try:
        with open(GROUPS_FILE, "r", encoding="utf-8") as file:
            groups = json.load(file)
        return get_group_from_record(groups.get(str(user_id)))
    except (OSError, json.JSONDecodeError) as error:
        logging.error("Ошибка чтения групп пользователей: %s", error)
        return None


async def save_user_group(user_id: int | str, name: str, group: str) -> None:
    normalized = normalize_group(group)
    if not normalized:
        raise ValueError(f"Неизвестная группа: {group}")
    groups = await load_json(GROUPS_FILE)
    groups[str(user_id)] = {
        "name": name,
        "group": normalized,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await save_json(groups, GROUPS_FILE)


async def remove_user_group(user_id: int | str) -> None:
    groups = await load_json(GROUPS_FILE)
    if groups.pop(str(user_id), None) is not None:
        await save_json(groups, GROUPS_FILE)


async def get_registration_draft(user_id: int | str) -> dict | None:
    drafts = await load_json(REGISTRATION_DRAFTS_FILE)
    draft = drafts.get(str(user_id))
    return dict(draft) if isinstance(draft, dict) else None


async def save_registration_draft(user_id: int | str, name: str) -> None:
    drafts = await load_json(REGISTRATION_DRAFTS_FILE)
    drafts[str(user_id)] = {
        "name": name,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await save_json(drafts, REGISTRATION_DRAFTS_FILE)


async def remove_registration_draft(user_id: int | str) -> None:
    drafts = await load_json(REGISTRATION_DRAFTS_FILE)
    if drafts.pop(str(user_id), None) is not None:
        await save_json(drafts, REGISTRATION_DRAFTS_FILE)
