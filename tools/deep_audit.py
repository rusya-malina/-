from __future__ import annotations

import ast
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MODULES = [
    "bot_context",
    "storage",
    "organization",
    "keyboards",
    "services",
    "health",
    "app_factory",
    "handlers.user",
    "handlers.admin",
    "handlers.teams",
    "handlers.kpi",
    "handlers.issuance",
    "handlers.uploads",
    "handlers.broadcast",
    "handlers.requests",
]
JSON_FILES = [
    "users.json",
    "kpi_data.json",
    "plans_config.json",
    "pending_requests.json",
    "team_requests.json",
    "teams.json",
    "issuance_data.json",
    "user_requests.json",
]


def load_json_files() -> list[str]:
    errors = []
    for name in JSON_FILES:
        path = ROOT / name
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                errors.append(f"{name}: top-level value is {type(data).__name__}, expected dict")
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    return errors


def source_audit() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for path in [ROOT / "bot.py", ROOT / "app_factory.py", ROOT / "bot_context.py", ROOT / "storage.py", ROOT / "organization.py", ROOT / "keyboards.py", ROOT / "services.py", ROOT / "health.py", *sorted((ROOT / "handlers").glob("*.py"))]:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        defs = [node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        result[str(path.relative_to(ROOT))] = defs
    return result


def main() -> None:
    print("AUDIT: importing modules")
    for module_name in MODULES:
        importlib.import_module(module_name)
        print(f"  OK {module_name}")

    print("AUDIT: building Application")
    from app_factory import build_application
    app = build_application("123456:TEST_TOKEN")
    print(f"  OK handler_groups={len(app.handlers)}")
    for group_index, handlers in app.handlers.items():
        print(f"  group={group_index} handlers={len(handlers)}")

    print("AUDIT: JSON files")
    errors = load_json_files()
    if errors:
        for error in errors:
            print(f"  ERROR {error}")
        raise SystemExit(1)
    print(f"  OK {len(JSON_FILES)} files")

    print("AUDIT: source definitions")
    for filename, defs in source_audit().items():
        print(f"  {filename}: {len(defs)} definitions")

    text = "\n".join(path.read_text(encoding="utf-8") for path in [ROOT / "bot_context.py", ROOT / "organization.py", ROOT / "keyboards.py", ROOT / "app_factory.py", *(ROOT / "handlers").glob("*.py")])
    checks = {
        "R LAMP present": "R LAMP" in text,
        "old team label absent outside migration/test": "К LAMP" not in text.replace('record.get("team") == "К LAMP"', "").replace('assert "К LAMP" not in TEAM_OPTIONS', ""),
        "user request button absent": "📝 Оставить заявку" not in text,
        "new admin requests button present": "📥 Заявки" in text,
        "requests callback present": "requests_callback" in text,
        "upload module present": (ROOT / "handlers/uploads.py").exists(),
    }
    for label, passed in checks.items():
        print(f"  {'OK' if passed else 'ERROR'} {label}")
    if not all(checks.values()):
        raise SystemExit(1)
    print("AUDIT: PASS")


if __name__ == "__main__":
    main()
