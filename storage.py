"""Асинхронный адаптер JSON-хранилищ бота."""
from bot_context import (
    ISSUANCE_FILE,
    ISSUANCE_SCHEMA_VERSION,
    PENDING_FILE,
    PLANS_FILE,
    TEAM_REQUESTS_FILE,
    TEAMS_FILE,
    asyncio,
    json,
    logging,
    os,
)


def _sync_load_json(filepath: str) -> dict:
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logging.error(f"Ошибка чтения файла {filepath}: {e}")
        return {}


def _sync_save_json(data: dict, filepath: str) -> None:
    temp_file = filepath + ".tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        if os.path.exists(filepath):
            os.remove(filepath)
        os.rename(temp_file, filepath)
    except OSError as e:
        logging.error(f"Ошибка сохранения файла {filepath}: {e}")


async def load_json(filepath: str) -> dict:
    return await asyncio.to_thread(_sync_load_json, filepath)


async def save_json(data: dict, filepath: str) -> None:
    await asyncio.to_thread(_sync_save_json, data, filepath)


def _reset_issuance_if_legacy() -> None:
    data = _sync_load_json(ISSUANCE_FILE)
    if data.get("_schema_version") != ISSUANCE_SCHEMA_VERSION:
        _sync_save_json({"_schema_version": ISSUANCE_SCHEMA_VERSION}, ISSUANCE_FILE)


def _migrate_team_label() -> None:
    """Переводит сохранённые заявки и команды со старого названия на R LAMP."""
    for filepath in (TEAM_REQUESTS_FILE, TEAMS_FILE):
        data = _sync_load_json(filepath)
        changed = False
        for record in data.values():
            if isinstance(record, dict) and record.get("team") == "К LAMP":
                record["team"] = "R LAMP"
                changed = True
        if changed:
            _sync_save_json(data, filepath)


async def load_pending() -> dict:
    return await load_json(PENDING_FILE)


async def save_pending(data: dict) -> None:
    await save_json(data, PENDING_FILE)


async def get_default_plans() -> dict:
    plans = await load_json(PLANS_FILE)
    return {
        "gt_plan": plans.get("gt_plan", 90.0),
        "micro_plan": plans.get("micro_plan", 128.0),
        "retrafic_plan": plans.get("retrafic_plan", 15.0),
    }
