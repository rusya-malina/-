from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from storage import migrate_json_schemas

if __name__ == "__main__":
    migrate_json_schemas()
    print("SCHEMA_MIGRATION_APPLIED")
