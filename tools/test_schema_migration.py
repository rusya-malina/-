from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import storage

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
        fixtures = {
            "users.json": {"excel_test": {"name": "Тестовый сотрудник"}},
            "groups.json": {"excel_test": {"name": "Тестовый сотрудник", "group": "A LAMP"}},
            "pending_requests.json": {},
            "team_requests.json": {},
            "user_requests.json": {},
            "teams.json": {},
            "registration_drafts.json": {},
            "issuance_data.json": {},
        }
        for filename, data in fixtures.items():
            (temp / filename).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        paths = {name.removesuffix(".json").upper() + "_FILE": str(temp / name) for name in JSON_FILES}
        with (
            patch.object(storage, "USERS_FILE", paths["USERS_FILE"]),
            patch.object(storage, "GROUPS_FILE", paths["GROUPS_FILE"]),
            patch.object(storage, "PENDING_FILE", paths["PENDING_REQUESTS_FILE"]),
            patch.object(storage, "TEAM_REQUESTS_FILE", paths["TEAM_REQUESTS_FILE"]),
            patch.object(storage, "USER_REQUESTS_FILE", paths["USER_REQUESTS_FILE"]),
            patch.object(storage, "TEAMS_FILE", paths["TEAMS_FILE"]),
            patch.object(storage, "REGISTRATION_DRAFTS_FILE", paths["REGISTRATION_DRAFTS_FILE"]),
            patch.object(storage, "ISSUANCE_FILE", paths["ISSUANCE_DATA_FILE"]),
        ):
            storage.migrate_json_schemas()

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
