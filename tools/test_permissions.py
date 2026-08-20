"""Regression tests for the centralized permission layer."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import ADMIN_ID
from permissions import (
    Permission,
    get_mode,
    has_permission,
    is_admin_mode,
    is_admin_user,
    main_menu_kwargs,
    set_admin_mode,
)


def test_admin_mode_is_identity_bound() -> None:
    context = SimpleNamespace(user_data={})
    assert is_admin_user(ADMIN_ID)
    assert not is_admin_user("not-admin")
    assert get_mode(ADMIN_ID, context) == "coor"
    assert not has_permission(ADMIN_ID, context, Permission.ADMIN_PANEL)

    set_admin_mode(context, True)
    assert get_mode(ADMIN_ID, context) == "admin"
    assert is_admin_mode(ADMIN_ID, context)
    assert has_permission(ADMIN_ID, context, Permission.ADMIN_PANEL)
    assert has_permission(ADMIN_ID, context, Permission.USER_MANAGEMENT)
    assert main_menu_kwargs(ADMIN_ID, context, "coor R") == {
        "group": "coor R",
        "admin_mode": True,
    }


def test_coor_mode_cannot_inherit_admin_permission() -> None:
    context = SimpleNamespace(user_data={"admin_mode": True})
    assert get_mode(ADMIN_ID + 1, context) == "coor"
    assert not is_admin_mode(ADMIN_ID + 1, context)
    assert not has_permission(ADMIN_ID + 1, context, Permission.DATA_UPLOAD)
    assert main_menu_kwargs(ADMIN_ID + 1, context, "coor A") == {
        "group": "coor A",
        "admin_mode": False,
    }


def test_disabling_admin_mode_keeps_context_but_removes_permissions() -> None:
    context = SimpleNamespace(user_data={"admin_mode": True, "name": "Admin"})
    set_admin_mode(context, False)
    assert context.user_data["name"] == "Admin"
    assert get_mode(ADMIN_ID, context) == "coor"
    assert not has_permission(ADMIN_ID, context, Permission.REGISTRATION_REQUESTS)


if __name__ == "__main__":
    test_admin_mode_is_identity_bound()
    test_coor_mode_cannot_inherit_admin_permission()
    test_disabling_admin_mode_keeps_context_but_removes_permissions()
    print("PERMISSIONS PASS")
