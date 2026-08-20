from __future__ import annotations

import ast
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSON_FILES = [
    "users.json",
    "groups.json",
    "pending_requests.json",
    "team_requests.json",
    "user_requests.json",
    "teams.json",
    "issuance_data.json",
    "kpi_data.json",
]


def summarize_file(filename: str) -> dict:
    path = ROOT / filename
    payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    records = list(payload.items()) if isinstance(payload, dict) else []
    sample = records[:2]
    return {
        "records": len(records),
        "top_level": type(payload).__name__,
        "sample_keys": [str(key) for key, _ in sample],
        "sample_value_types": [type(value).__name__ for _, value in sample],
        "sample_values": sample,
    }


def write_sites() -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for path in [ROOT / "storage.py", *sorted((ROOT / "handlers").glob("*.py")), ROOT / "roles.py"]:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"save_json", "update_json", "update_many_json", "save_pending", "update_pending"}:
                result[node.func.id].append(f"{path.relative_to(ROOT)}:{node.lineno}")
    return dict(result)


def main() -> None:
    print(json.dumps({"files": {name: summarize_file(name) for name in JSON_FILES}, "write_sites": write_sites()}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
