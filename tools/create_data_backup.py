from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from config import GROUPS_FILE, KPI_FILE, USERS_FILE

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (USERS_FILE, GROUPS_FILE, KPI_FILE)
timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup_dir = ROOT / "backups" / timestamp
backup_dir.mkdir(parents=True, exist_ok=False)

manifest = {
    "created_at": datetime.now(timezone.utc).isoformat(),
    "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    "files": {},
}

for source_name in SOURCE_FILES:
    source = Path(source_name)
    if not source.exists():
        continue
    relative_name = source.name
    target = backup_dir / relative_name
    shutil.copy2(source, target)
    data = json.loads(source.read_text(encoding="utf-8"))
    manifest["files"][relative_name] = {
        "records": len(data) if isinstance(data, dict) else None,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }

(backup_dir / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(backup_dir)
print(json.dumps(manifest, ensure_ascii=False, indent=2))
