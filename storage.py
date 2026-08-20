"""Асинхронный адаптер JSON-хранилищ бота."""
from collections.abc import Callable, Iterable
from contextlib import AsyncExitStack

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
from data_models import (
    group_name,
    make_group_record,
    make_team_record,
    make_user_record,
    normalize_issuance_record,
    registration_request,
    team_request,
    user_name,
    user_request,
)
from errors import StorageError

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
    except (json.JSONDecodeError, OSError) as error:
        logging.error("Ошибка чтения файла %s: %s", filepath, error)
        raise StorageError(f"Не удалось прочитать JSON-хранилище: {filepath}") from error


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
    except OSError as error:
        logging.error("Ошибка сохранения файла %s: %s", filepath, error)
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except OSError:
            pass
        raise StorageError(f"Не удалось сохранить JSON-хранилище: {filepath}") from error


def load_json_sync(filepath: str) -> dict:
    """Read-only synchronous access for startup and keyboard rendering."""
    return _sync_load_json(filepath)


def save_json_sync(data: dict, filepath: str) -> None:
    """Synchronous atomic write for tiny startup/session metadata files."""
    _sync_save_json(data, filepath)


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


async def update_many_json(filepaths: Iterable[str], mutator: Callable[[dict[str, dict]], object]):
    """Serialize a related multi-file read-modify-write operation.

    Locks are acquired in sorted path order to avoid deadlocks when concurrent
    handlers update overlapping JSON stores.
    """
    paths = sorted(set(filepaths))
    async with AsyncExitStack() as stack:
        for filepath in paths:
            await stack.enter_async_context(_get_json_lock(filepath))
        data = {filepath: await load_json(filepath) for filepath in paths}
        result = mutator(data)
        for filepath in paths:
            await save_json(data[filepath], filepath)
        return result


def migrate_json_schemas() -> None:
    """Upgrade legacy JSON values to canonical schema-versioned records."""
    users = _sync_load_json("users.json")
    migrated_users = {}
    for user_id, record in users.items():
        if isinstance(record, dict) and record.get("schema_version") == 1 and record.get("name"):
            migrated_users[str(user_id)] = record
        else:
            migrated_users[str(user_id)] = make_user_record(user_name(record, str(user_id)))
    if migrated_users != users:
        _sync_save_json(migrated_users, "users.json")

    groups = _sync_load_json("groups.json")
    migrated_groups = {}
    for user_id, record in groups.items():
        group = group_name(record)
        name = user_name(record, user_name(migrated_users.get(str(user_id)), str(user_id)))
        migrated_groups[str(user_id)] = make_group_record(name, group or "")
    if migrated_groups != groups:
        _sync_save_json(migrated_groups, "groups.json")

    for filepath, normalizer in (
        (PENDING_FILE, registration_request),
        (TEAM_REQUESTS_FILE, team_request),
        ("user_requests.json", user_request),
    ):
        data = _sync_load_json(filepath)
        migrated = {str(key): normalizer(record, user_id=key) for key, record in data.items()}
        if migrated != data:
            _sync_save_json(migrated, filepath)

    drafts = _sync_load_json("registration_drafts.json")
    migrated_drafts = {
        str(key): {
            "schema_version": 1,
            "name": user_name(record, str(key)),
            "updated_at": (record.get("updated_at") if isinstance(record, dict) else None) or "",
        }
        for key, record in drafts.items()
    }
    if migrated_drafts != drafts:
        _sync_save_json(migrated_drafts, "registration_drafts.json")

    teams = _sync_load_json(TEAMS_FILE)
    migrated_teams = {
        str(key): make_team_record(user_name(record, str(key)), group_name(record) or "")
        for key, record in teams.items()
    }
    if migrated_teams != teams:
        _sync_save_json(migrated_teams, TEAMS_FILE)

    issuance = _sync_load_json(ISSUANCE_FILE)
    migrated_issuance = {"_schema_version": ISSUANCE_SCHEMA_VERSION}
    for key, record in issuance.items():
        if key != "_schema_version":
            migrated_issuance[str(key)] = normalize_issuance_record(record)
    if migrated_issuance != issuance:
        _sync_save_json(migrated_issuance, ISSUANCE_FILE)


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
