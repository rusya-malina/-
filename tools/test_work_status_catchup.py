"""Regression test for missed daily poll recovery after a restart."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

from handlers import work_status


class _FakeDateTime:
    @classmethod
    def now(cls, _timezone):
        return datetime(2026, 9, 24, 15, 42)


class _WednesdayDateTime:
    @classmethod
    def now(cls, _timezone):
        return datetime(2026, 9, 23, 15, 42)


def test_catchup_runs_after_daily_time() -> None:
    calls: list[object] = []

    async def fake_poll(context):
        calls.append(context)

    original_datetime = work_status.datetime
    original_poll = work_status.send_work_status_poll_job
    work_status.datetime = _FakeDateTime
    work_status.send_work_status_poll_job = fake_poll
    context = SimpleNamespace()
    try:
        asyncio.run(work_status.send_missed_work_status_poll_job(context))
    finally:
        work_status.datetime = original_datetime
        work_status.send_work_status_poll_job = original_poll

    assert calls == [context]


def test_catchup_skips_non_poll_days() -> None:
    calls: list[object] = []

    async def fake_poll(context):
        calls.append(context)

    original_datetime = work_status.datetime
    original_poll = work_status.send_work_status_poll_job
    work_status.datetime = _WednesdayDateTime
    work_status.send_work_status_poll_job = fake_poll
    context = SimpleNamespace()
    try:
        asyncio.run(work_status.send_missed_work_status_poll_job(context))
    finally:
        work_status.datetime = original_datetime
        work_status.send_work_status_poll_job = original_poll

    assert calls == []


if __name__ == "__main__":
    test_catchup_runs_after_daily_time()
    test_catchup_skips_non_poll_days()
    print("WORK_STATUS_CATCHUP PASS")
