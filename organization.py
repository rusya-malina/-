from __future__ import annotations

from collections import OrderedDict
import re

from bot_context import ADMIN_ID, TEAM_OPTIONS

ORG_STRUCTURE = {
    "MNG": {"level": 1, "parent": None, "children": ("SPV",)},
    "SPV": {"level": 2, "parent": "MNG", "children": ("coor A", "coor R")},
    "coor A": {"level": 3, "parent": "SPV", "children": ("A LAMP",)},
    "coor R": {"level": 3, "parent": "SPV", "children": ("R LAMP",)},
    "A LAMP": {"level": 4, "parent": "coor A", "children": ()},
    "R LAMP": {"level": 4, "parent": "coor R", "children": ()},
}

MANAGEMENT_GROUPS = frozenset({"MNG", "SPV", "coor A", "coor R"})
TEAM_GROUPS = frozenset({"A LAMP", "R LAMP"})


def normalize_employee_name(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _record_group(record) -> str | None:
    if isinstance(record, dict):
        return record.get("group") or record.get("team")
    return record or None


def _is_numeric_id(user_id: str) -> bool:
    return str(user_id).isdigit()


def _preferred_user_id(current_id: str | None, candidate_id: str) -> str:
    if not current_id:
        return candidate_id
    if _is_numeric_id(candidate_id) and not _is_numeric_id(current_id):
        return candidate_id
    return current_id


def build_employee_registry(
    users: dict,
    groups: dict,
    kpi_data: dict | None = None,
    issuance_data: dict | None = None,
) -> list[dict]:
    """Собирает единый список сотрудников и объединяет дубли по нормализованному имени.

    Числовой Telegram ID имеет приоритет над сервисным ``excel_*`` ID. Все исходные
    идентификаторы сохраняются в ``aliases`` для корректной связи с выдачами.
    """
    records: OrderedDict[str, dict] = OrderedDict()

    def add_record(user_id, name, group=None):
        user_id = str(user_id or "").strip()
        name = str(name or "").strip()
        normalized_name = normalize_employee_name(name)
        if not user_id or not normalized_name or normalized_name == "nan":
            return
        record = records.get(normalized_name)
        if record is None:
            record = {
                "user_id": user_id,
                "name": name,
                "group": group,
                "aliases": [user_id],
                "name_key": normalized_name,
            }
            records[normalized_name] = record
        else:
            if user_id not in record["aliases"]:
                record["aliases"].append(user_id)
            previous_id = record["user_id"]
            record["user_id"] = _preferred_user_id(previous_id, user_id)
            if _is_numeric_id(user_id) and not _is_numeric_id(previous_id):
                record["name"] = name
            if group and (not record.get("group") or _is_numeric_id(user_id)):
                record["group"] = group

    # users.json is the primary roster. Numeric IDs are processed first so that
    # a Telegram account wins over an earlier Excel-only placeholder.
    user_items = sorted(
        users.items(),
        key=lambda item: (not _is_numeric_id(str(item[0])), normalize_employee_name(item[1]), str(item[0])),
    )
    for user_id, name in user_items:
        group = _record_group(groups.get(str(user_id)))
        add_record(user_id, name, group)

    # These fallbacks keep reports complete if a legacy snapshot contains a
    # group/KPI/issuance record before users.json has been rebuilt.
    for user_id, group_record in groups.items():
        if str(user_id).startswith("_"):
            continue
        group = _record_group(group_record)
        name = group_record.get("name") if isinstance(group_record, dict) else None
        if name:
            add_record(user_id, name, group)

    for key, kpi_record in (kpi_data or {}).items():
        if isinstance(kpi_record, dict):
            name = kpi_record.get("original_name", key)
            normalized_name = normalize_employee_name(name)
            if normalized_name not in records:
                add_record(f"kpi_{normalized_name}", name)

    for user_id, issuance_record in (issuance_data or {}).items():
        if str(user_id).startswith("_") or not isinstance(issuance_record, dict):
            continue
        add_record(user_id, issuance_record.get("name"), _record_group(groups.get(str(user_id))))

    return sorted(records.values(), key=lambda item: item["name"].casefold())


def get_employee_by_id(
    user_id: int | str,
    users: dict,
    groups: dict,
    kpi_data: dict | None = None,
    issuance_data: dict | None = None,
) -> dict | None:
    user_id = str(user_id)
    for employee in build_employee_registry(users, groups, kpi_data, issuance_data):
        if user_id in employee["aliases"]:
            return employee
    return None


def merge_employee_issuance(employee: dict | None, issuance_data: dict) -> dict:
    """Объединяет выдачи по Telegram-ID и старым Excel-ID одного сотрудника."""
    merged = {"mints_issued": 0.0, "sticks_issued": 0.0, "history": []}
    if not employee:
        return merged
    for alias in employee.get("aliases", []):
        record = issuance_data.get(str(alias), {})
        if not isinstance(record, dict):
            continue
        merged["mints_issued"] += float(record.get("mints_issued", 0) or 0)
        merged["sticks_issued"] += float(record.get("sticks_issued", 0) or 0)
        merged["history"].extend(record.get("history", []) or [])
    return merged


def get_scope_groups(group: str | None) -> frozenset[str]:
    """Возвращает группы, которые руководитель может просматривать."""
    if group == "MNG":
        return frozenset(TEAM_OPTIONS)
    if group == "SPV":
        return frozenset({"SPV", "coor A", "coor R", "A LAMP", "R LAMP"})
    if group == "coor A":
        return frozenset({"coor A", "A LAMP"})
    if group == "coor R":
        return frozenset({"coor R", "R LAMP"})
    if group in TEAM_GROUPS:
        return frozenset({group})
    return frozenset()


def can_view_group(actor_group: str | None, target_group: str | None) -> bool:
    return target_group in get_scope_groups(actor_group)


def is_management_group(group: str | None) -> bool:
    return group in MANAGEMENT_GROUPS


def is_admin_mode(user_id: int | str, context) -> bool:
    return str(user_id) == str(ADMIN_ID) and bool(getattr(context, "user_data", {}).get("admin_mode"))


def get_visible_users(
    actor_id: int | str,
    users: dict,
    groups: dict,
    admin_mode: bool = False,
    exclude_user_id: int | str | None = None,
    kpi_data: dict | None = None,
    issuance_data: dict | None = None,
) -> list[dict]:
    """Возвращает единый список сотрудников в зоне ответственности актёра."""
    if str(actor_id) == str(ADMIN_ID) and admin_mode:
        scope = frozenset(TEAM_OPTIONS)
    else:
        actor_record = groups.get(str(actor_id), {})
        actor_group = _record_group(actor_record)
        scope = get_scope_groups(actor_group)

    visible = []
    for employee in build_employee_registry(users, groups, kpi_data, issuance_data):
        if exclude_user_id is not None and str(exclude_user_id) in employee["aliases"]:
            continue
        if employee.get("group") in scope:
            visible.append(
                {
                    "user_id": employee["user_id"],
                    "name": employee["name"],
                    "group": employee["group"],
                    "aliases": employee["aliases"],
                    "name_key": employee["name_key"],
                }
            )
    return visible
