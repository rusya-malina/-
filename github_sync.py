"""Private GitHub backup for runtime state.

The code repository contains application code only. Runtime JSON and uploaded files are
stored locally under ``BOT_DATA_DIR`` and mirrored to a separate private repository when
``GITHUB_SYNC_TOKEN`` is configured.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import quote

import requests

from config import (
    ADMIN_SESSION_FILE,
    BASE_DIR,
    DELETED_USERS_FILE,
    GROUPS_FILE,
    ISSUANCE_FILE,
    KPI_FILE,
    LATEST_ISSUANCE_FILE,
    LATEST_KPI_FILE,
    PENDING_FILE,
    PLANS_FILE,
    REGISTRATION_DRAFTS_FILE,
    TEAM_KPI_FILE,
    TEAM_REQUESTS_FILE,
    TEAMS_FILE,
    TRAINING_HISTORY_FILE,
    TRAINING_ONE_FILE,
    TRAINING_TWO_FILE,
    USER_REQUESTS_FILE,
    USERS_FILE,
)

LOGGER = logging.getLogger(__name__)
GITHUB_API_ROOT = "https://api.github.com"
SYNC_PATHS = (KPI_FILE, LATEST_KPI_FILE)
TRAINING_SYNC_PATHS = (TRAINING_HISTORY_FILE, TRAINING_ONE_FILE, TRAINING_TWO_FILE)
JSON_SYNC_PATHS = (
    USERS_FILE,
    GROUPS_FILE,
    KPI_FILE,
    TEAM_KPI_FILE,
    PLANS_FILE,
    PENDING_FILE,
    TEAM_REQUESTS_FILE,
    USER_REQUESTS_FILE,
    REGISTRATION_DRAFTS_FILE,
    DELETED_USERS_FILE,
    TEAMS_FILE,
    ISSUANCE_FILE,
    TRAINING_HISTORY_FILE,
    ADMIN_SESSION_FILE,
)
DATA_SYNC_PATHS = tuple(
    dict.fromkeys(
        (
            *JSON_SYNC_PATHS,
            LATEST_KPI_FILE,
            LATEST_ISSUANCE_FILE,
            TRAINING_ONE_FILE,
            TRAINING_TWO_FILE,
        )
    )
)
_SYNC_LOCK = asyncio.Lock()


def _enabled() -> bool:
    token = os.getenv("GITHUB_SYNC_TOKEN", "").strip()
    enabled = os.getenv("GITHUB_SYNC_ENABLED", "true").strip().lower()
    return bool(token and _repo()) and enabled not in {"0", "false", "no", "off"}


def _repo() -> str:
    return os.getenv("GITHUB_SYNC_REPO", "").strip().strip("/")


def _branch() -> str:
    return os.getenv("GITHUB_SYNC_BRANCH", "main").strip() or "main"


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {os.environ['GITHUB_SYNC_TOKEN'].strip()}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "kpi-telegram-bot-sync",
    }


def _repo_path(path: str) -> str:
    local_path = Path(path)
    base_path = Path(BASE_DIR)
    try:
        if base_path != Path(".") and not local_path.is_absolute():
            return local_path.relative_to(base_path).as_posix()
        if local_path.is_absolute():
            return local_path.resolve().relative_to(base_path.resolve()).as_posix()
    except ValueError:
        return local_path.name
    return local_path.as_posix()


def _api_url(path: str) -> str:
    encoded_path = "/".join(quote(part, safe="") for part in _repo_path(path).split("/"))
    return f"{GITHUB_API_ROOT}/repos/{_repo()}/contents/{encoded_path}"


def _request(method: str, path: str, **kwargs) -> requests.Response:
    params = kwargs.pop("params", {})
    if method.upper() == "GET":
        params.setdefault("ref", _branch())
    return requests.request(
        method,
        _api_url(path),
        headers=_headers(),
        params=params,
        timeout=(10, 45),
        **kwargs,
    )


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
        temporary_path = tmp.name
    os.replace(temporary_path, destination)


def _validate_sync_content(path: str, content: bytes) -> None:
    if _repo_path(path).lower().endswith(".json"):
        parsed = json.loads(content.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise TypeError(f"Remote JSON file is not an object: {_repo_path(path)}")


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


def _restore_paths(paths: Iterable[str]) -> bool:
    if not _enabled():
        LOGGER.info("GitHub state restore disabled: GITHUB_SYNC_TOKEN is not configured")
        return False

    failed = False
    restored = 0
    for path in dict.fromkeys(paths):
        try:
            remote = _get_remote(path)
            if remote is None:
                LOGGER.info("No remote state yet: %s", _repo_path(path))
                continue
            content, _sha = remote
            _validate_sync_content(path, content)
            _write_atomic(path, content)
            restored += 1
        except Exception:
            failed = True
            LOGGER.exception("Failed to restore state from GitHub: %s", _repo_path(path))
    LOGGER.info("Restored %s runtime state file(s) from GitHub repository %s", restored, _repo())
    return not failed


def _sync_paths_local(paths: Iterable[str]) -> bool:
    if not _enabled():
        LOGGER.warning("GitHub state sync skipped: GITHUB_SYNC_TOKEN is not configured")
        return False

    existing_paths = [path for path in dict.fromkeys(paths) if os.path.exists(path)]
    if not existing_paths:
        LOGGER.warning("Cannot sync state; local files are missing")
        return False

    try:
        for path in existing_paths:
            local_content = _read_local(path)
            _validate_sync_content(path, local_content)
            remote = _get_remote(path)
            sha = remote[1] if remote else None
            _put_remote(path, local_content, sha, f"Persist bot data: {_repo_path(path)}")
        LOGGER.info("Runtime state synchronized to GitHub repository %s", _repo())
        return True
    except Exception:
        LOGGER.exception("Failed to synchronize runtime state to GitHub")
        return False


def restore_data_state_sync() -> bool:
    """Restore all available runtime JSON and uploaded files before polling starts."""
    return _restore_paths(DATA_SYNC_PATHS)


def sync_data_state_sync(filepaths: Iterable[str] | None = None) -> bool:
    """Synchronous runtime sync for tiny startup/session metadata writes."""
    paths = tuple(filepaths) if filepaths is not None else DATA_SYNC_PATHS
    return _sync_paths_local(paths)


async def sync_data_state(filepaths: Iterable[str] | None = None) -> bool:
    """Upload selected runtime state without blocking Telegram handlers."""
    paths = tuple(filepaths) if filepaths is not None else DATA_SYNC_PATHS
    async with _SYNC_LOCK:
        return await asyncio.to_thread(_sync_paths_local, paths)


def restore_kpi_state_sync() -> bool:
    """Backward-compatible restore for KPI files."""
    return _restore_paths(SYNC_PATHS)


async def sync_kpi_state() -> bool:
    """Backward-compatible upload for KPI files."""
    return await sync_data_state(SYNC_PATHS)


def restore_training_history_sync() -> bool:
    """Backward-compatible restore for training files."""
    return _restore_paths(TRAINING_SYNC_PATHS)


def _sync_training_history_local() -> bool:
    """Backward-compatible synchronous helper for training tests and tooling."""
    return _sync_paths_local(TRAINING_SYNC_PATHS)


async def sync_training_history() -> bool:
    """Backward-compatible upload for training files."""
    return await sync_data_state(TRAINING_SYNC_PATHS)


__all__ = [
    "DATA_SYNC_PATHS",
    "JSON_SYNC_PATHS",
    "SYNC_PATHS",
    "TRAINING_SYNC_PATHS",
    "restore_data_state_sync",
    "restore_kpi_state_sync",
    "restore_training_history_sync",
    "sync_data_state",
    "sync_data_state_sync",
    "_sync_training_history_local",
    "sync_kpi_state",
    "sync_training_history",
]
