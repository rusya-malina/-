"""Regression tests for the Telegram webhook transport."""
from __future__ import annotations

import asyncio
import http.client
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.webhook_server import WebhookServer


class FakeBot:
    async def set_webhook(self, **kwargs) -> None:
        self.webhook_kwargs = kwargs

    async def delete_webhook(self, **kwargs) -> None:
        self.deleted_kwargs = kwargs


class FakeApplication:
    def __init__(self) -> None:
        self.bot = FakeBot()
        self.update_queue = asyncio.Queue()
        self.running = False
        self.initialized = False
        self.started = False
        self.stopped = False
        self.shutdown_called = False

    async def initialize(self) -> None:
        self.initialized = True

    async def start(self) -> None:
        self.running = True
        self.started = True

    async def stop(self) -> None:
        self.running = False
        self.stopped = True

    async def shutdown(self) -> None:
        self.shutdown_called = True


def request(port: int, method: str, path: str, body: bytes = b"", secret: str | None = None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Content-Length": str(len(body))}
    if secret is not None:
        headers["X-Telegram-Bot-Api-Secret-Token"] = secret
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    payload = response.read()
    connection.close()
    return response.status, json.loads(payload) if payload else {}


def test_webhook_server_routes_and_deduplicates() -> None:
    application = FakeApplication()
    server = WebhookServer(
        port=0,
        application=application,
        path="/telegram/webhook",
        secret="test-secret",
        public_url="https://example.test",
    )
    server.start()
    assert server.http_server is not None
    port = server.http_server.server_address[1]
    try:
        assert request(port, "GET", "/healthz")[0] == 200
        assert request(port, "HEAD", "/")[0] == 200
        assert request(port, "POST", "/telegram/webhook", b"{}", "wrong")[0] == 403

        payload = json.dumps({"update_id": 1001, "message": {"message_id": 1, "date": 1, "chat": {"id": 1, "type": "private"}, "text": "/start", "from": {"id": 1, "is_bot": False, "first_name": "Test"}}}).encode()
        status, result = request(port, "POST", "/telegram/webhook", payload, "test-secret")
        assert status == 200
        assert result["duplicate"] is False
        duplicate_status, duplicate_result = request(
            port, "POST", "/telegram/webhook", payload, "test-secret"
        )
        assert duplicate_status == 200
        assert duplicate_result["duplicate"] is True

        loop = server.application_loop
        assert loop is not None
        queued = asyncio.run_coroutine_threadsafe(application.update_queue.get(), loop).result(timeout=5)
        assert queued.update_id == 1001
    finally:
        server.close()
        time.sleep(0.05)
        assert application.shutdown_called is True
        assert application.stopped is True


if __name__ == "__main__":
    test_webhook_server_routes_and_deduplicates()
    print("WEBHOOK_SERVER PASS")
