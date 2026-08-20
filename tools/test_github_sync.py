from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import github_sync


class Response:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def encoded(content: bytes, sha: str = "remote-sha") -> dict:
    return {
        "content": base64.b64encode(content).decode("ascii"),
        "sha": sha,
    }


def test_restore_and_sync() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        kpi_path = directory / "kpi_data.json"
        excel_path = directory / "uploaded_data" / "latest_kpi.xlsx"
        github_sync.KPI_FILE = str(kpi_path)
        github_sync.LATEST_KPI_FILE = str(excel_path)
        github_sync.SYNC_PATHS = (str(kpi_path), str(excel_path))
        os.environ["GITHUB_SYNC_TOKEN"] = "test-token"
        os.environ["GITHUB_SYNC_REPO"] = "rusya-malina/-"
        os.environ["GITHUB_SYNC_BRANCH"] = "main"

        remote_kpi = b'{"employee":{"gt_fact":99}}'
        remote_excel = b"remote-xlsx-bytes"
        responses = {
            str(kpi_path): encoded(remote_kpi),
            str(excel_path): encoded(remote_excel),
        }

        def restore_request(method, url, **kwargs):
            assert method == "GET"
            path = str(kpi_path) if "kpi_data.json" in url else str(excel_path)
            return Response(200, responses[path])

        original_request = github_sync.requests.request
        github_sync.requests.request = restore_request
        try:
            assert github_sync.restore_kpi_state_sync() is True
        finally:
            github_sync.requests.request = original_request

        assert kpi_path.read_bytes() == remote_kpi
        assert excel_path.read_bytes() == remote_excel

        kpi_path.write_text(json.dumps({"employee": {"gt_fact": 100}}), encoding="utf-8")
        excel_path.write_bytes(b"new-xlsx-bytes")
        puts = []

        def sync_request(method, url, **kwargs):
            if method == "GET":
                return Response(404)
            assert method == "PUT"
            puts.append(kwargs["json"])
            return Response(200, {})

        github_sync.requests.request = sync_request
        try:
            assert asyncio.run(github_sync.sync_kpi_state()) is True
        finally:
            github_sync.requests.request = original_request

        assert len(puts) == 2
        assert base64.b64decode(puts[0]["content"]).startswith(b"{")
        assert base64.b64decode(puts[1]["content"]) == b"new-xlsx-bytes"


if __name__ == "__main__":
    test_restore_and_sync()
    print("github sync tests passed")
