"""Regression tests for automatic Telegram polling recovery."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from telegram.error import Conflict, TelegramError

from recovery import handle_application_error


class FakeApplication:
    def __init__(self) -> None:
        self.stop_calls = 0
        self.bot_data = {}

    def stop_running(self) -> None:
        self.stop_calls += 1


async def test_conflict_stops_application() -> None:
    application = FakeApplication()
    context = SimpleNamespace(application=application, error=Conflict("duplicate polling"))
    await handle_application_error(None, context)
    assert application.stop_calls == 1
    assert application.bot_data["polling_conflict_detected"] is True


async def test_regular_telegram_error_does_not_stop_application() -> None:
    application = FakeApplication()
    context = SimpleNamespace(application=application, error=TelegramError("temporary error"))
    await handle_application_error(None, context)
    assert application.stop_calls == 0


async def main() -> None:
    await test_conflict_stops_application()
    await test_regular_telegram_error_does_not_stop_application()
    print("POLLING_RECOVERY PASS")


if __name__ == "__main__":
    asyncio.run(main())
