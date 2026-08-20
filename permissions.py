"""Единый слой разрешений и режима работы бота.

Модуль не зависит от Telegram handlers и поэтому может использоваться из
keyboards, handlers и тестов без циклических импортов. Единственным источником
истины для режима администратора является ``context.user_data['admin_mode']``.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from config import ADMIN_ID

ADMIN_MODE_KEY = "admin_mode"
Mode = Literal["admin", "coor"]


class Permission(StrEnum):
    """Прикладные разрешения, которые требуют включённого /admin режима."""

    ADMIN_PANEL = "admin_panel"
    USER_MANAGEMENT = "user_management"
    REGISTRATION_REQUESTS = "registration_requests"
    TEAM_APPROVAL = "team_approval"
    DATA_UPLOAD = "data_upload"
    BROADCAST = "broadcast"
    ISSUANCE = "issuance"
    KPI_MANAGEMENT = "kpi_management"


def is_admin_user(user_id: int | str | None) -> bool:
    """Возвращает True только для настроенного Telegram ID администратора."""
    return user_id is not None and str(user_id) == str(ADMIN_ID)


def _user_data(context: Any) -> dict[str, Any]:
    """Безопасно возвращает mutable user_data для реального и тестового context."""
    data = getattr(context, "user_data", None)
    return data if isinstance(data, dict) else {}


def set_admin_mode(context: Any, enabled: bool) -> None:
    """Устанавливает режим администратора без удаления остальных user_data."""
    data = _user_data(context)
    data[ADMIN_MODE_KEY] = bool(enabled)


def get_mode(user_id: int | str | None, context: Any) -> Mode:
    """Возвращает эффективный режим: admin возможен только для ADMIN_ID."""
    if is_admin_user(user_id) and bool(_user_data(context).get(ADMIN_MODE_KEY)):
        return "admin"
    return "coor"


def is_admin_mode(user_id: int | str | None, context: Any) -> bool:
    """Совместимый predicate для handlers: пользователь реально в /admin."""
    return get_mode(user_id, context) == "admin"


def has_permission(
    user_id: int | str | None,
    context: Any,
    permission: Permission,
) -> bool:
    """Проверяет разрешение через единый режим, а не через локальные флаги."""
    admin_permissions = {
        Permission.ADMIN_PANEL,
        Permission.USER_MANAGEMENT,
        Permission.REGISTRATION_REQUESTS,
        Permission.TEAM_APPROVAL,
        Permission.DATA_UPLOAD,
        Permission.BROADCAST,
        Permission.ISSUANCE,
        Permission.KPI_MANAGEMENT,
    }
    if permission in admin_permissions:
        return is_admin_mode(user_id, context)
    return False


def main_menu_kwargs(user_id: int | str | None, context: Any, group: str | None = None) -> dict[str, Any]:
    """Возвращает параметры главного меню без возможности потерять admin mode."""
    return {
        "group": group,
        "admin_mode": is_admin_mode(user_id, context),
    }


def permission_denied_text(permission: Permission) -> str:
    """Единое сообщение для отказа в административном доступе."""
    if permission == Permission.REGISTRATION_REQUESTS:
        return "⛔️ Раздел заявок доступен только в режиме /admin."
    if permission == Permission.USER_MANAGEMENT:
        return "⛔️ Управление пользователями доступно только в режиме /admin."
    return "⛔️ Эта функция доступна только в режиме /admin."


__all__ = [
    "ADMIN_MODE_KEY",
    "Mode",
    "Permission",
    "get_mode",
    "has_permission",
    "is_admin_mode",
    "is_admin_user",
    "main_menu_kwargs",
    "permission_denied_text",
    "set_admin_mode",
]
