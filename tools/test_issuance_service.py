"""Contract tests for issuance application use cases."""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application.issuance_service import IssuanceService
from repositories.json_repository import JsonRepository


def test_issuance_service() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "issuance.json"
        path.write_text(json.dumps({}), encoding="utf-8")
        service = IssuanceService(JsonRepository(str(path)))

        async def scenario() -> None:
            first = await service.issue(42, "Test Employee", "mints", "10,5", 99)
            assert first.ok
            second = await service.issue(42, "Test Employee", "sticks", 3, 99)
            assert second.ok
            data = json.loads(path.read_text(encoding="utf-8"))
            record = data["42"]
            assert record["mints_issued"] == 10.5
            assert record["sticks_issued"] == 3.0
            assert len(record["history"]) == 2
            invalid = await service.issue(42, "Test Employee", "mints", 0, 99)
            assert not invalid.ok

        asyncio.run(scenario())


if __name__ == "__main__":
    test_issuance_service()
    print("ISSUANCE_SERVICE PASS")
