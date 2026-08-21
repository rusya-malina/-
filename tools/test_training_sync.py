from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import github_sync


def test_training_history_sync() -> None:
    with tempfile.TemporaryDirectory() as directory:
        history_path = Path(directory) / "training_history.json"
        history_path.write_text(
            json.dumps({"100": {"schema_version": 1, "name": "Employee", "deliveries": []}}),
            encoding="utf-8",
        )
        remote_content = history_path.read_bytes()
        uploaded: dict[str, bytes] = {}

        def fake_remote(_path: str):
            return remote_content, "remote-sha"

        def fake_put(path: str, content: bytes, sha: str | None, message: str) -> None:
            uploaded.update({"path": path, "content": content, "sha": sha, "message": message})

        with (
            patch.object(github_sync, "TRAINING_SYNC_PATHS", (str(history_path),)),
            patch.object(github_sync, "_enabled", return_value=True),
            patch.object(github_sync, "_get_remote", side_effect=fake_remote),
            patch.object(github_sync, "_put_remote", side_effect=fake_put),
        ):
            assert github_sync._sync_training_history_local() is True
            assert uploaded["content"] == remote_content
            assert uploaded["sha"] == "remote-sha"
            assert uploaded["message"] == "Persist bot data: training_history.json"

        history_path.write_text("{}", encoding="utf-8")
        with (
            patch.object(github_sync, "TRAINING_SYNC_PATHS", (str(history_path),)),
            patch.object(github_sync, "_enabled", return_value=True),
            patch.object(github_sync, "_get_remote", return_value=(remote_content, "remote-sha")),
        ):
            assert github_sync.restore_training_history_sync() is True
            assert json.loads(history_path.read_text(encoding="utf-8")) == json.loads(remote_content.decode("utf-8"))


if __name__ == "__main__":
    test_training_history_sync()
    print("TRAINING_SYNC PASS")
