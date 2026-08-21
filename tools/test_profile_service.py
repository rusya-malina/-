"""Contract tests for atomic profile rename across linked records."""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application.profile_service import ProfileService
from repositories.json_repository import JsonRepository


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


async def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        users = root / "users.json"
        groups = root / "groups.json"
        kpi = root / "kpi_data.json"
        issuance = root / "issuance_data.json"
        write_json(users, {"123": {"name": "Старое Имя", "created_at": "created"}})
        write_json(groups, {"123": {"name": "Старое Имя", "group": "A LAMP"}})
        write_json(
            kpi,
            {
                "старое имя": {
                    "original_name": "Старое Имя",
                    "gt_plan": 90,
                    "gt_fact": 12,
                }
            },
        )
        write_json(
            issuance,
            {
                "123": {"name": "Старое Имя", "mints_issued": 10, "sticks_issued": 2, "history": []},
                "excel_старое имя": {"name": "Старое Имя", "mints_issued": 3, "sticks_issued": 1, "history": []},
            },
        )
        service = ProfileService(
            users=JsonRepository(str(users)),
            groups=JsonRepository(str(groups)),
            kpi=JsonRepository(str(kpi)),
            issuance=JsonRepository(str(issuance)),
        )

        result = await service.rename(123, "Новое Имя")
        assert result.ok
        assert json.loads(users.read_text(encoding="utf-8"))["123"]["name"] == "Новое Имя"
        assert json.loads(groups.read_text(encoding="utf-8"))["123"]["name"] == "Новое Имя"
        saved_kpi = json.loads(kpi.read_text(encoding="utf-8"))
        assert "старое имя" not in saved_kpi
        assert saved_kpi["новое имя"]["original_name"] == "Новое Имя"
        saved_issuance = json.loads(issuance.read_text(encoding="utf-8"))
        assert saved_issuance["123"]["name"] == "Новое Имя"
        assert saved_issuance["excel_старое имя"]["name"] == "Новое Имя"

        unchanged = await service.rename(123, "Новое Имя")
        assert unchanged.ok and unchanged.code == "unchanged"
        write_json(users, {"123": {"name": "Новое Имя"}, "456": {"name": "Занятое Имя"}})
        conflict = await service.rename(123, "Занятое Имя")
        assert not conflict.ok and conflict.code == "conflict"
        missing = await service.rename(999, "Ещё Имя")
        assert not missing.ok and missing.code == "not_found"

    print("PROFILE_SERVICE PASS")


if __name__ == "__main__":
    asyncio.run(main())
