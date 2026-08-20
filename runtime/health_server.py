"""Render health server lifecycle."""
from __future__ import annotations

import threading
from dataclasses import dataclass

from bot_context import ThreadingHTTPServer
from health import HealthHandler


@dataclass
class HealthServer:
    port: int
    server: ThreadingHTTPServer | None = None
    thread: threading.Thread | None = None

    def start(self) -> None:
        self.server = ThreadingHTTPServer(("0.0.0.0", self.port), HealthHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self) -> None:
        if self.server is None:
            return
        self.server.shutdown()
        self.server.server_close()
        self.server = None
        self.thread = None


__all__ = ["HealthServer"]
