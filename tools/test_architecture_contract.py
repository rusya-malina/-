from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PRODUCTION_FILES = [ROOT / "app_factory.py", ROOT / "bot.py", ROOT / "health.py", ROOT / "keyboards.py", ROOT / "organization.py", ROOT / "roles.py", ROOT / "services.py", ROOT / "storage.py", *sorted((ROOT / "handlers").glob("*.py"))]


def main() -> None:
    wildcard_imports = []
    for path in PRODUCTION_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
                wildcard_imports.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not wildcard_imports, wildcard_imports
    assert (ROOT / "config.py").exists()
    assert (ROOT / "states.py").exists()
    storage = ast.parse((ROOT / "storage.py").read_text(encoding="utf-8"))
    names = {node.name for node in storage.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert {"load_json_sync", "update_json", "update_many_json"} <= names
    print("ARCHITECTURE_CONTRACT PASS")


if __name__ == "__main__":
    main()
