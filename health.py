"""Минимальный HTTP health endpoint для Render."""
from bot_context import BaseHTTPRequestHandler


class HealthHandler(BaseHTTPRequestHandler):
    """Минимальный endpoint для health check Render Web Service."""

    _HEALTH_PATHS = frozenset(("/", "/healthz"))

    def _send_health_response(self, include_body: bool) -> None:
        if self.path not in self._HEALTH_PATHS:
            self.send_response(404)
            self.end_headers()
            return

        body = b"OK"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def do_GET(self):
        self._send_health_response(include_body=True)

    def do_HEAD(self):
        self._send_health_response(include_body=False)

    def log_message(self, format, *args):
        return
