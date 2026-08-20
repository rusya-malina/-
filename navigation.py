"""Централизованная навигация между admin/coor и подменю."""
from __future__ import annotations

import os
from typing import Any

from keyboards import get_main_keyboard
from permissions import main_menu_kwargs


def main_menu_markup(user_id: int | str, context: Any, group: str | None = None):
    """Строит главное меню по эффективному режиму текущего context.

    Ни один caller не передаёт ``admin_mode`` вручную: его вычисляет permission
    layer и сверяет с Telegram ID администратора.
    """
    return get_main_keyboard(user_id, **main_menu_kwargs(user_id, context, group))


def clear_pending_import(context: Any) -> None:
    """Удаляет staged Excel import и временный файл при отмене навигации."""
    data = getattr(context, "user_data", None)
    if not isinstance(data, dict):
        return
    staged = data.pop("pending_excel_import", None)
    if isinstance(staged, dict):
        temp_path = staged.get("temp_path")
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def clear_navigation_state(context: Any) -> None:
    """Очищает временное состояние navigation/import, не меняя права."""
    data = getattr(context, "user_data", None)
    if not isinstance(data, dict):
        return
    clear_pending_import(context)
    for key in ("navigation_return_state", "navigation_return_menu"):
        data.pop(key, None)


__all__ = ["clear_navigation_state", "clear_pending_import", "main_menu_markup"]
