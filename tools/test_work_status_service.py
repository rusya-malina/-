"""Regression tests for daily work status and pair invitations."""

from __future__ import annotations

import asyncio

from application import work_status_service as service


def test_daily_pair_invitation_flow(monkeypatch):
    users = {
        "101": {"name": "Аня Один"},
        "102": {"name": "Бэлла Два"},
        "201": {"name": "Рита Три"},
        "301": {"name": "Коор A"},
    }
    groups = {
        "101": {"name": "Аня Один", "group": "A LAMP"},
        "102": {"name": "Бэлла Два", "group": "A LAMP"},
        "201": {"name": "Рита Три", "group": "R LAMP"},
        "301": {"name": "Коор A", "group": "coor A"},
    }
    state = {}

    async def fake_load(path):
        if path == service.USERS_FILE:
            return users
        if path == service.GROUPS_FILE:
            return groups
        return state

    async def fake_update(path, mutator):
        mutator(state)

    monkeypatch.setattr(service, "load_json", fake_load)
    monkeypatch.setattr(service, "update_json", fake_update)
    monkeypatch.setattr(service, "_today", lambda: "2026-09-23")

    async def scenario():
        assert (await service.set_work_status("101", "working"))["ok"]
        assert await service.get_pair_candidates("101") == []

        assert (await service.set_work_status("102", "working"))["ok"]
        candidates = await service.get_pair_candidates("101")
        assert [item["name"] for item in candidates] == ["Бэлла Два"]

        invite = await service.create_pair_invite("101", "102")
        assert invite["ok"]

        accepted = await service.accept_pair_invite(invite["invite_id"], "102")
        assert accepted["ok"]
        assert (await service.get_today_status("101"))["pair_name"] == "Бэлла Два"
        assert (await service.get_today_status("102"))["pair_name"] == "Аня Один"
        assert await service.get_pair_candidates("101") == []

        overview = await service.get_coordinator_overview()
        assert len(overview["pairs"]) == 1
        assert overview["pairs"][0]["first_name"] == "Аня Один"
        assert overview["pairs"][0]["second_name"] == "Бэлла Два"
        assert all(item["name"] == "Рита Три" for item in overview["not_working"])

    asyncio.run(scenario())


def test_rejected_invitation_returns_candidate(monkeypatch):
    users = {"101": {"name": "Аня Один"}, "102": {"name": "Бэлла Два"}}
    groups = {
        "101": {"name": "Аня Один", "group": "A LAMP"},
        "102": {"name": "Бэлла Два", "group": "A LAMP"},
    }
    state = {}

    async def fake_load(path):
        if path == service.USERS_FILE:
            return users
        if path == service.GROUPS_FILE:
            return groups
        return state

    async def fake_update(path, mutator):
        mutator(state)

    monkeypatch.setattr(service, "load_json", fake_load)
    monkeypatch.setattr(service, "update_json", fake_update)
    monkeypatch.setattr(service, "_today", lambda: "2026-09-23")

    async def scenario():
        await service.set_work_status("101", "working")
        await service.set_work_status("102", "working")
        invite = await service.create_pair_invite("101", "102")
        rejected = await service.reject_pair_invite(invite["invite_id"], reason="user_rejected")
        assert rejected["ok"]
        candidates = await service.get_pair_candidates("101")
        assert [item["user_id"] for item in candidates] == ["102"]

    asyncio.run(scenario())
