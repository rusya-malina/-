"""Regression tests for issuance group scoping."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import handlers.issuance as issuance_handler
from config import GROUPS_FILE, USERS_FILE


def callback_ids(markup):
    return {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }


async def main() -> None:
    users = {
        "101": "Алина A",
        "102": "Роман R",
        "103": "Светлана coor",
        "104": "Менеджер MNG",
    }
    groups = {
        "101": {"group": "A LAMP"},
        "102": {"group": "R LAMP"},
        "103": {"group": "coor A"},
        "104": {"group": "MNG"},
    }
    original_load_json = issuance_handler.load_json

    async def fake_load_json(path):
        if path == USERS_FILE:
            return users
        if path == GROUPS_FILE:
            return groups
        raise AssertionError(f"unexpected storage path: {path}")

    issuance_handler.load_json = fake_load_json
    try:
        context = SimpleNamespace(user_data={})
        a_markup = await issuance_handler._get_issuance_users_markup(context, {"A LAMP"})
        r_markup = await issuance_handler._get_issuance_users_markup(context, {"R LAMP"})
        assert callback_ids(a_markup) == {"issue_user:101", "issue_cancel"}
        assert callback_ids(r_markup) == {"issue_user:102", "issue_cancel"}
        issuance_handler.is_admin_mode = lambda user_id, _context: False
        issuance_handler.get_user_group = lambda user_id: asyncio.sleep(0, result="coor A")
        assert await issuance_handler._allowed_issuance_groups(5001, context) == {"A LAMP"}
        assert await issuance_handler._target_is_allowed(5001, "101", context)
        assert not await issuance_handler._target_is_allowed(5001, "102", context)
        issuance_handler.get_user_group = lambda user_id: asyncio.sleep(0, result="coor R")
        assert await issuance_handler._allowed_issuance_groups(5002, context) == {"R LAMP"}
        assert await issuance_handler._target_is_allowed(5002, "102", context)
        assert not await issuance_handler._target_is_allowed(5002, "101", context)
    finally:
        issuance_handler.load_json = original_load_json


if __name__ == "__main__":
    asyncio.run(main())
    print("ISSUANCE_SCOPE PASS")

