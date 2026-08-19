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


_JSON_LOCKS: dict[str, asyncio.Lock] = {}


def replace_latest_file(source_path: str, latest_path: str) -> None:
    """Атомарно делает source_path единственным актуальным файлом."""
    parent = os.path.dirname(os.path.abspath(latest_path))
    os.makedirs(parent, exist_ok=True)
    os.replace(source_path, latest_path)


def _get_json_lock(filepath: str) -> asyncio.Lock:
    return _JSON_LOCKS.setdefault(filepath, asyncio.Lock())


def _sync_load_json(filepath: str) -> dict:
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                logging.error("Ожидался JSON-объект в %s, получен %s", filepath, type(data).__name__)
                return {}
            return data
    except (json.JSONDecodeError, OSError) as e:
        logging.error("Ошибка чтения файла %s: %s", filepath, e)
        return {}


def _sync_save_json(data: dict, filepath: str) -> None:
    temp_file = filepath + ".tmp"
    try:
        parent = os.path.dirname(os.path.abspath(filepath))
        os.makedirs(parent, exist_ok=True)
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_file, filepath)
    except OSError as e:
        logging.error("Ошибка сохранения файла %s: %s", filepath, e)
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except OSError:
            pass


async def load_json(filepath: str) -> dict:
    return await asyncio.to_thread(_sync_load_json, filepath)


async def save_json(data: dict, filepath: str) -> None:
    await asyncio.to_thread(_sync_save_json, data, filepath)


async def update_json(filepath: str, mutator):
    """Атомарно выполняет read-modify-write под блокировкой одного файла."""
    async with _get_json_lock(filepath):
        data = await load_json(filepath)
        result = mutator(data)
        await save_json(data, filepath)
        return result


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


async def update_pending(mutator):
    return await update_json(PENDING_FILE, mutator)


async def save_pending(data: dict) -> None:
    await save_json(data, PENDING_FILE)


async def get_default_plans() -> dict:
    plans = await load_json(PLANS_FILE)
    return {
        "gt_plan": plans.get("gt_plan", 90.0),
        "micro_plan": plans.get("micro_plan", 128.0),
        "retrafic_plan": plans.get("retrafic_plan", 15.0),
    }
