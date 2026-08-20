"""Минимальный HTTP health endpoint для Render."""
from bot_context import BaseHTTPRequestHandler


class HealthHandler(BaseHTTPRequestHandler):
    """Минимальный endpoint для health check Render Web Service."""

    def do_GET(self):
        if self.path not in ("/", "/healthz"):
            self.send_response(404)
            self.end_headers()
            return

        body = b"OK"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return
