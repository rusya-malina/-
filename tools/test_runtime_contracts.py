"""Contract tests for runtime startup, health and polling supervisor boundaries."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.polling_supervisor import PollingSupervisor


class FakeApplication:
    def __init__(self):
        self.stop_calls = 0
        self.poll_calls = 0

    def stop_running(self):
        self.stop_calls += 1

    def run_polling(self, **kwargs):
        self.poll_calls += 1
        assert kwargs["stop_signals"] == ()
        raise RuntimeError("test stop")


def test_supervisor_stop_delegates_to_application() -> None:
    app = FakeApplication()
    supervisor = PollingSupervisor("token", lambda _: app, retry_delay=0)
    supervisor.current_app = app
    supervisor.stop()
    assert supervisor.stop_event.is_set()
    assert app.stop_calls == 1


def test_supervisor_run_stops_after_runtime_signal() -> None:
    app = FakeApplication()
    supervisor = PollingSupervisor("token", lambda _: app, retry_delay=0)
    supervisor.stop_event.set()
    supervisor.run()
    assert app.poll_calls == 0


if __name__ == "__main__":
    test_supervisor_stop_delegates_to_application()
    test_supervisor_run_stops_after_runtime_signal()
    print("RUNTIME_CONTRACTS PASS")
