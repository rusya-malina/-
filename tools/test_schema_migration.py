from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from storage import migrate_json_schemas

JSON_FILES = (
    "users.json",
    "groups.json",
    "pending_requests.json",
    "team_requests.json",
    "user_requests.json",
    "teams.json",
    "registration_drafts.json",
    "issuance_data.json",
)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="schema_migration_") as temp_dir:
        temp = Path(temp_dir)
        for filename in JSON_FILES:
            shutil.copy2(ROOT / filename, temp / filename)
        original_cwd = Path.cwd()
        os.chdir(temp)
        try:
            migrate_json_schemas()
        finally:
            os.chdir(original_cwd)

        users = json.loads((temp / "users.json").read_text(encoding="utf-8"))
        groups = json.loads((temp / "groups.json").read_text(encoding="utf-8"))
        issuance = json.loads((temp / "issuance_data.json").read_text(encoding="utf-8"))
        assert users and all(isinstance(record, dict) and record.get("schema_version") == 1 for record in users.values())
        assert groups and all(isinstance(record, dict) and record.get("schema_version") == 1 for record in groups.values())
        assert issuance.get("_schema_version") == 2
        assert all(key == "_schema_version" or record.get("schema_version") == 1 for key, record in issuance.items())
        print("SCHEMA_MIGRATION PASS")


if __name__ == "__main__":
    main()
