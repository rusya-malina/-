from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from errors import StorageError
from storage import _sync_load_json, _sync_save_json


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="storage_errors_") as temp_dir:
        temp = Path(temp_dir)
        broken = temp / "broken.json"
        broken.write_text("{not-json", encoding="utf-8")
        try:
            _sync_load_json(str(broken))
        except StorageError:
            pass
        else:
            raise AssertionError("broken JSON must raise StorageError")

        blocked = temp / "missing" / "store.json"
        blocked.parent.write_text("not-a-directory", encoding="utf-8")
        try:
            _sync_save_json({"ok": True}, str(blocked))
        except StorageError:
            pass
        else:
            raise AssertionError("failed JSON write must raise StorageError")
    print("STORAGE_ERRORS PASS")


if __name__ == "__main__":
    main()
