"""Regression tests for the centralized permission layer."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import permissions
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


def test_persisted_admin_mode_restores_on_fresh_context() -> None:
    with tempfile.NamedTemporaryFile(prefix="permissions_", suffix=".json", delete=False) as session_file:
        session_path = session_file.name
    original_path = permissions.ADMIN_SESSION_FILE
    original_loaded = permissions._PERSISTENCE_LOADED
    original_mode = permissions._PERSISTED_ADMIN_MODE
    try:
        permissions.ADMIN_SESSION_FILE = session_path
        permissions._PERSISTENCE_LOADED = False
        permissions._PERSISTED_ADMIN_MODE = False
        first_context = SimpleNamespace(user_data={})
        set_admin_mode(first_context, True, user_id=ADMIN_ID)
        fresh_context = SimpleNamespace(user_data={})
        assert get_mode(ADMIN_ID, fresh_context) == "admin"
        set_admin_mode(fresh_context, False, user_id=ADMIN_ID)
        assert get_mode(ADMIN_ID, fresh_context) == "coor"
    finally:
        permissions.ADMIN_SESSION_FILE = original_path
        permissions._PERSISTENCE_LOADED = original_loaded
        permissions._PERSISTED_ADMIN_MODE = original_mode
        Path(session_path).unlink(missing_ok=True)


def test_disabling_admin_mode_keeps_context_but_removes_permissions() -> None:
    context = SimpleNamespace(user_data={"admin_mode": True, "name": "Admin"})
    set_admin_mode(context, False)
    assert context.user_data["name"] == "Admin"
    assert get_mode(ADMIN_ID, context) == "coor"
    assert not has_permission(ADMIN_ID, context, Permission.REGISTRATION_REQUESTS)


if __name__ == "__main__":
    test_admin_mode_is_identity_bound()
    test_coor_mode_cannot_inherit_admin_permission()
    test_persisted_admin_mode_restores_on_fresh_context()
    test_disabling_admin_mode_keeps_context_but_removes_permissions()
    print("PERMISSIONS PASS")
