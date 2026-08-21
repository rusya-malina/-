"""Contract tests for the production health HTTP handler."""
from __future__ import annotations

import http.client
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from health import HealthHandler


def request(server: ThreadingHTTPServer, method: str, path: str) -> tuple[int, dict[str, str], bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, headers, body = request(server, "GET", "/")
        assert status == 200
        assert body == b"OK"
        assert headers["Content-Length"] == "2"

        status, headers, body = request(server, "GET", "/healthz")
        assert status == 200
        assert body == b"OK"
        assert headers["Content-Length"] == "2"

        status, headers, body = request(server, "HEAD", "/")
        assert status == 200
        assert body == b""
        assert headers["Content-Length"] == "2"

        status, headers, body = request(server, "HEAD", "/healthz")
        assert status == 200
        assert body == b""
        assert headers["Content-Length"] == "2"

        status, _headers, body = request(server, "HEAD", "/missing")
        assert status == 404
        assert body == b""
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    print("HEALTH_ENDPOINTS PASS")


if __name__ == "__main__":
    main()
