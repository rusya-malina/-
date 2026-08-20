"""Temporary durable storage bridge for KPI data using the GitHub Contents API.

The repository must be treated as a temporary public backup until the bot is
migrated to private object storage or a database. Tokens are read only from
runtime environment variables and are never written to the repository.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import tempfile
from pathlib import Path
from urllib.parse import quote

import requests

from bot_context import KPI_FILE, LATEST_KPI_FILE

LOGGER = logging.getLogger(__name__)
GITHUB_API_ROOT = "https://api.github.com"
SYNC_PATHS = (KPI_FILE, LATEST_KPI_FILE)
_SYNC_LOCK = asyncio.Lock()


def _enabled() -> bool:
    token = os.getenv("GITHUB_SYNC_TOKEN", "").strip()
    enabled = os.getenv("GITHUB_SYNC_ENABLED", "true").strip().lower()
    return bool(token) and enabled not in {"0", "false", "no", "off"}


def _repo() -> str:
    return os.getenv("GITHUB_SYNC_REPO", "rusya-malina/-").strip().strip("/")


def _branch() -> str:
    return os.getenv("GITHUB_SYNC_BRANCH", "main").strip() or "main"


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {os.environ['GITHUB_SYNC_TOKEN'].strip()}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "kpi-telegram-bot-sync",
    }


def _api_url(path: str) -> str:
    encoded_path = "/".join(quote(part, safe="") for part in path.split("/"))
    return f"{GITHUB_API_ROOT}/repos/{_repo()}/contents/{encoded_path}"


def _request(method: str, path: str, **kwargs) -> requests.Response:
    params = kwargs.pop("params", {})
    if method.upper() == "GET":
        params.setdefault("ref", _branch())
    response = requests.request(
        method,
        _api_url(path),
        headers=_headers(),
        params=params,
        timeout=(10, 45),
        **kwargs,
    )
    return response


def _decode_contents(payload: dict) -> bytes:
    encoded = str(payload.get("content", "")).replace("\n", "")
    if not encoded:
        raise ValueError("GitHub Contents API returned empty content")
    return base64.b64decode(encoded, validate=True)


def _read_local(path: str) -> bytes:
    with open(path, "rb") as source:
        return source.read()


def _write_atomic(path: str, content: bytes) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=f".{destination.name}.", dir=destination.parent, delete=False) as tmp:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        temp_path = tmp.name
    os.replace(temp_path, destination)


def _validate_remote_kpi_json(content: bytes) -> None:
    parsed = json.loads(content.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise TypeError("Remote kpi_data.json is not a JSON object")


def _get_remote(path: str) -> tuple[bytes, str | None] | None:
    response = _request("GET", path)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    payload = response.json()
    return _decode_contents(payload), payload.get("sha")


def _put_remote(path: str, content: bytes, sha: str | None, message: str) -> None:
    body = {
        "message": message,
        "content": base64.b64encode(content).decode("ascii"),
        "branch": _branch(),
    }
    if sha:
        body["sha"] = sha
    response = _request("PUT", path, json=body)
    response.raise_for_status()


def _restore_sync() -> bool:
    if not _enabled():
        LOGGER.info("GitHub KPI restore disabled: GITHUB_SYNC_TOKEN is not configured")
        return False

    restored = 0
    for path in SYNC_PATHS:
        try:
            remote = _get_remote(path)
            if remote is None:
                LOGGER.warning("GitHub KPI file not found: %s", path)
                continue
            content, _sha = remote
            if path == KPI_FILE:
                _validate_remote_kpi_json(content)
            _write_atomic(path, content)
            restored += 1
        except Exception:
            LOGGER.exception("Failed to restore KPI file from GitHub: %s", path)
    return restored == len(SYNC_PATHS)


def _sync_local_state() -> bool:
    if not _enabled():
        LOGGER.warning("GitHub KPI sync skipped: GITHUB_SYNC_TOKEN is not configured")
        return False

    missing = [path for path in SYNC_PATHS if not os.path.exists(path)]
    if missing:
        LOGGER.error("Cannot sync KPI state; local files are missing: %s", ", ".join(missing))
        return False

    try:
        for path in SYNC_PATHS:
            local_content = _read_local(path)
            if path == KPI_FILE:
                _validate_remote_kpi_json(local_content)
            remote = _get_remote(path)
            sha = remote[1] if remote else None
            _put_remote(
                path,
                local_content,
                sha,
                f"Persist latest KPI data: {Path(path).name}",
            )
        LOGGER.info("Latest KPI state synchronized to GitHub repository %s", _repo())
        return True
    except Exception:
        LOGGER.exception("Failed to synchronize latest KPI state to GitHub")
        return False


def restore_kpi_state_sync() -> bool:
    """Restore the latest remote KPI state before polling starts."""
    return _restore_sync()


async def sync_kpi_state() -> bool:
    """Upload the current KPI JSON and latest Excel without blocking handlers."""
    async with _SYNC_LOCK:
        return await asyncio.to_thread(_sync_local_state)
