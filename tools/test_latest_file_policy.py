from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from storage import replace_latest_file


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    users = ROOT / "users.json"
    kpi = ROOT / "kpi_data.json"
    users_before = digest(users)
    kpi_before = digest(kpi)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        latest = temp / "latest.xlsx"
        first = temp / "first.xlsx"
        second = temp / "second.xlsx"
        first.write_bytes(b"first workbook")
        replace_latest_file(str(first), str(latest))
        assert latest.read_bytes() == b"first workbook"
        assert not first.exists()

        second.write_bytes(b"second workbook")
        replace_latest_file(str(second), str(latest))
        assert latest.read_bytes() == b"second workbook"
        assert not second.exists()

    assert digest(users) == users_before
    assert digest(kpi) == kpi_before
    print("latest file policy tests passed")


if __name__ == "__main__":
    main()
