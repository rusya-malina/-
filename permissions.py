"""Единый слой разрешений и режима работы бота.

Модуль не зависит от Telegram handlers и используется как совместимый adapter
для нового pure domain permission policy. Режим администратора хранится в session
context и в отдельном persistent session metadata.
"""
from __future__ import annotations

from typing import Any

from bot_context import logging
from config import ADMIN_ID, ADMIN_SESSION_FILE
from domain.models import Mode, Permission
from errors import StorageError
from storage import load_json_sync, save_json_sync

ADMIN_MODE_KEY = "admin_mode"
PERSISTED_MODE_SCHEMA_VERSION = 1
_PERSISTENCE_LOADED = False
_PERSISTED_ADMIN_MODE = False


def is_admin_user(user_id: int | str | None) -> bool:
    """Возвращает True только для настроенного Telegram ID администратора."""
    return user_id is not None and str(user_id) == str(ADMIN_ID)


def _user_data(context: Any) -> dict[str, Any]:
    """Безопасно возвращает mutable user_data для реального и тестового context."""
    data = getattr(context, "user_data", None)
    return data if isinstance(data, dict) else {}


def load_persisted_admin_mode() -> bool:
    """Загружает admin/coor mode из tiny atomic session metadata один раз."""
    global _PERSISTENCE_LOADED, _PERSISTED_ADMIN_MODE
    if _PERSISTENCE_LOADED:
        return _PERSISTED_ADMIN_MODE
    try:
        record = load_json_sync(ADMIN_SESSION_FILE)
        _PERSISTED_ADMIN_MODE = (
            record.get("schema_version") == PERSISTED_MODE_SCHEMA_VERSION
            and str(record.get("admin_id")) == str(ADMIN_ID)
            and bool(record.get(ADMIN_MODE_KEY))
        )
    except StorageError:
        logging.exception("Не удалось восстановить admin mode из %s", ADMIN_SESSION_FILE)
        _PERSISTED_ADMIN_MODE = False
    _PERSISTENCE_LOADED = True
    return _PERSISTED_ADMIN_MODE


def _persist_admin_mode(enabled: bool) -> None:
    global _PERSISTENCE_LOADED, _PERSISTED_ADMIN_MODE
    try:
        save_json_sync(
            {
                "schema_version": PERSISTED_MODE_SCHEMA_VERSION,
                "admin_id": str(ADMIN_ID),
                ADMIN_MODE_KEY: bool(enabled),
            },
            ADMIN_SESSION_FILE,
        )
        from github_sync import sync_data_state_sync

        sync_data_state_sync((ADMIN_SESSION_FILE,))
        _PERSISTED_ADMIN_MODE = bool(enabled)
        _PERSISTENCE_LOADED = True
    except StorageError:
        logging.exception("Не удалось сохранить admin mode в %s", ADMIN_SESSION_FILE)


def set_admin_mode(context: Any, enabled: bool, user_id: int | str | None = None) -> None:
    """Устанавливает режим и сохраняет его только для реального администратора."""
    data = _user_data(context)
    data[ADMIN_MODE_KEY] = bool(enabled)
    if user_id is not None and is_admin_user(user_id):
        _persist_admin_mode(enabled)


def get_mode(user_id: int | str | None, context: Any) -> Mode:
    """Возвращает эффективный режим: admin возможен только для ADMIN_ID."""
    if not is_admin_user(user_id):
        return "coor"
    data = _user_data(context)
    if ADMIN_MODE_KEY in data:
        return "admin" if bool(data[ADMIN_MODE_KEY]) else "coor"
    if load_persisted_admin_mode():
        data[ADMIN_MODE_KEY] = True
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
    "load_persisted_admin_mode",
    "main_menu_kwargs",
    "permission_denied_text",
    "set_admin_mode",
]
