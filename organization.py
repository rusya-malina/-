"""Организационная иерархия и read-only области видимости пользователей."""

from __future__ import annotations

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
) -> list[dict]:
    """Возвращает только numeric Telegram users в зоне ответственности актёра."""
    if str(actor_id) == str(ADMIN_ID) and admin_mode:
        scope = frozenset(TEAM_OPTIONS)
    else:
        actor_record = groups.get(str(actor_id), {})
        actor_group = actor_record.get("group") if isinstance(actor_record, dict) else actor_record
        scope = get_scope_groups(actor_group)

    visible = []
    for user_id, name in users.items():
        user_id = str(user_id)
        if exclude_user_id is not None and user_id == str(exclude_user_id):
            continue
        if not user_id.isdigit():
            continue
        record = groups.get(user_id, {})
        user_group = record.get("group") if isinstance(record, dict) else record
        if user_group in scope:
            visible.append({"user_id": user_id, "name": str(name), "group": user_group})
    return sorted(visible, key=lambda item: item["name"].casefold())
