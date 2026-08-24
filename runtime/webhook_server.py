"""HTTP webhook server for Telegram updates and Render health checks."""
from __future__ import annotations

import asyncio
import json
import threading
from collections import deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from telegram import Update
from telegram.error import TelegramError

from bot_context import logging

MAX_WEBHOOK_BODY_BYTES = 1_000_000
WEBHOOK_READY_TIMEOUT = 30
WEBHOOK_ENQUEUE_TIMEOUT = 5
SEEN_UPDATE_IDS_LIMIT = 2_000


class _WebhookRequestHandler(BaseHTTPRequestHandler):
    """Serve health checks and authenticated Telegram webhook requests."""

    server: "_WebhookHTTPServer"

    def _write_json(self, status: int, payload: dict[str, Any], include_body: bool = True) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def _health(self, include_body: bool) -> None:
        if urlsplit(self.path).path not in {"/", "/healthz"}:
            self._write_json(404, {"ok": False, "error": "not found"}, include_body)
            return
        self._write_json(200, {"ok": True, "status": "running"}, include_body)

    def do_GET(self) -> None:
        self._health(include_body=True)

    def do_HEAD(self) -> None:
        self._health(include_body=False)

    def do_POST(self) -> None:
        if urlsplit(self.path).path != self.server.owner.path:
            self._write_json(404, {"ok": False, "error": "not found"})
            return

        if self.headers.get("X-Telegram-Bot-Api-Secret-Token") != self.server.owner.secret:
            self._write_json(403, {"ok": False, "error": "forbidden"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            content_length = -1
        if content_length < 0 or content_length > MAX_WEBHOOK_BODY_BYTES:
            self._write_json(413, {"ok": False, "error": "invalid request size"})
            return

        try:
            payload = json.loads(self.rfile.read(content_length))
            if not isinstance(payload, dict):
                raise ValueError("Telegram update must be a JSON object")
            accepted = self.server.owner.enqueue_update(payload)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as error:
            logging.warning("Rejected malformed Telegram webhook payload: %s", error)
            self._write_json(400, {"ok": False, "error": "invalid JSON"})
            return
        except RuntimeError:
            logging.exception("Telegram webhook application is not ready")
            self._write_json(503, {"ok": False, "error": "application unavailable"})
            return

        self._write_json(200, {"ok": True, "duplicate": not accepted})

    def log_message(self, format, *args) -> None:
        return


class _WebhookHTTPServer(ThreadingHTTPServer):
    """HTTP server carrying a reference to the webhook lifecycle owner."""

    def __init__(self, address, owner: "WebhookServer") -> None:
        self.owner = owner
        super().__init__(address, _WebhookRequestHandler)


@dataclass
class WebhookServer:
    """Run PTB Application and its authenticated webhook listener once."""

    port: int
    application: Any
    path: str
    secret: str
    public_url: str
    http_server: _WebhookHTTPServer | None = None
    http_thread: threading.Thread | None = None
    application_thread: threading.Thread | None = None
    application_loop: asyncio.AbstractEventLoop | None = None
    ready: threading.Event = field(default_factory=threading.Event)
    stopped: threading.Event = field(default_factory=threading.Event)
    startup_error: BaseException | None = None
    _seen_update_ids: deque[int] = field(default_factory=lambda: deque(maxlen=SEEN_UPDATE_IDS_LIMIT))
    _seen_update_id_set: set[int] = field(default_factory=set)
    _seen_lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self) -> None:
        self.http_server = _WebhookHTTPServer(("0.0.0.0", self.port), self)
        self.http_thread = threading.Thread(
            target=self.http_server.serve_forever,
            name="telegram-webhook-http",
            daemon=True,
        )
        self.http_thread.start()

        self.application_thread = threading.Thread(
            target=self._run_application,
            name="telegram-webhook-application",
            daemon=True,
        )
        self.application_thread.start()
        if not self.ready.wait(WEBHOOK_READY_TIMEOUT):
            raise RuntimeError("Telegram webhook application did not start in time")
        if self.startup_error is not None:
            raise RuntimeError("Telegram webhook application failed to start") from self.startup_error
        logging.info("Telegram webhook server started at %s", self.public_url)

    def wait(self) -> None:
        self.stopped.wait()

    def close(self) -> None:
        if self.stopped.is_set():
            return
        self.stopped.set()
        if self.http_server is not None:
            self.http_server.shutdown()
            self.http_server.server_close()
            self.http_server = None
        loop = self.application_loop
        if loop is not None and not loop.is_closed():
            try:
                future = asyncio.run_coroutine_threadsafe(self._stop_application(), loop)
                future.result(timeout=WEBHOOK_READY_TIMEOUT)
            except (OSError, RuntimeError, TimeoutError, TelegramError):
                logging.exception("Failed to stop Telegram webhook application gracefully")
            try:
                if not loop.is_closed():
                    loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:
                logging.info("Telegram webhook event loop was already closed during shutdown")
        elif loop is not None:
            logging.info("Telegram webhook event loop was already closed during shutdown")
        if self.http_thread is not None:
            self.http_thread.join(timeout=WEBHOOK_READY_TIMEOUT)
            self.http_thread = None
        if self.application_thread is not None:
            self.application_thread.join(timeout=WEBHOOK_READY_TIMEOUT)
            self.application_thread = None
        logging.info("Telegram webhook server stopped gracefully")

    def install_signal_handlers(self) -> None:
        import signal

        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)

    def enqueue_update(self, payload: dict[str, Any]) -> bool:
        update_id = payload.get("update_id")
        if isinstance(update_id, int):
            with self._seen_lock:
                if update_id in self._seen_update_id_set:
                    return False
                if len(self._seen_update_ids) == self._seen_update_ids.maxlen:
                    expired = self._seen_update_ids.popleft()
                    self._seen_update_id_set.discard(expired)
                self._seen_update_ids.append(update_id)
                self._seen_update_id_set.add(update_id)

        loop = self.application_loop
        if loop is None or not loop.is_running() or not self.application.running:
            raise RuntimeError("Telegram webhook application is not running")
        update = Update.de_json(payload, self.application.bot)
        future = asyncio.run_coroutine_threadsafe(self.application.update_queue.put(update), loop)
        future.result(timeout=WEBHOOK_ENQUEUE_TIMEOUT)
        return True

    def _run_application(self) -> None:
        loop = asyncio.new_event_loop()
        self.application_loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.application.initialize())
            loop.run_until_complete(
                self.application.bot.set_webhook(
                    url=f"{self.public_url}{self.path}",
                    secret_token=self.secret,
                    drop_pending_updates=False,
                    allowed_updates=["message", "callback_query", "my_chat_member"],
                )
            )
            loop.run_until_complete(self.application.start())
            self.ready.set()
            logging.info("Telegram webhook application started")
            loop.run_forever()
        except (OSError, RuntimeError, TimeoutError, TelegramError, ValueError) as error:
            self.startup_error = error
            self.ready.set()
            logging.exception("Telegram webhook application failed")
        finally:
            if self.application.running:
                loop.run_until_complete(self.application.stop())
            if self.application_loop is not None:
                loop.run_until_complete(self.application.shutdown())
            loop.close()
            self.application_loop = None

    async def _stop_application(self) -> None:
        if self.application.running:
            await self.application.stop()
        if self.application_loop is not None and self.application_loop.is_running():
            self.application_loop.stop()

    def _handle_shutdown(self, signum, _frame) -> None:
        logging.info("Shutdown signal %s received", signum)
        self.close()


__all__ = ["WebhookServer"]
