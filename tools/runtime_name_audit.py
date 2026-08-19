from __future__ import annotations

import builtins
import dis
import importlib
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MODULES = [
    "bot",
    "app_factory",
    "storage",
    "keyboards",
    "services",
    "health",
    "handlers.user",
    "handlers.admin",
    "handlers.teams",
    "handlers.kpi",
    "handlers.issuance",
    "handlers.uploads",
    "handlers.broadcast",
    "handlers.requests",
]


def main() -> None:
    failures = []
    for module_name in MODULES:
        module = importlib.import_module(module_name)
        module_globals = module.__dict__
        for name, value in module_globals.items():
            if not inspect.isfunction(value):
                continue
            if value.__module__ != module_name:
                continue
            global_loads = {
                instruction.argval
                for instruction in dis.get_instructions(value)
                if instruction.opname in {"LOAD_GLOBAL", "LOAD_NAME"}
            }
            missing = sorted(
                symbol
                for symbol in global_loads
                if symbol not in module_globals and not hasattr(builtins, symbol)
            )
            if missing:
                failures.append(f"{module_name}.{name}: {', '.join(missing)}")
    if failures:
        print("RUNTIME NAME AUDIT: FAIL")
        print("\n".join(failures))
        raise SystemExit(1)
    print(f"RUNTIME NAME AUDIT: PASS ({len(MODULES)} modules)")


if __name__ == "__main__":
    main()
