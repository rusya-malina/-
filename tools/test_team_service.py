"""Contract tests for team application use cases."""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application.team_service import TeamService
from repositories.json_repository import JsonRepository


def test_team_service() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        requests_path = root / "requests.json"
        teams_path = root / "teams.json"
        requests_path.write_text("{}", encoding="utf-8")
        teams_path.write_text("{}", encoding="utf-8")
        service = TeamService(JsonRepository(str(requests_path)), JsonRepository(str(teams_path)))

        async def scenario() -> None:
            created = await service.create_request(42, "Test Employee", "A LAMP")
            assert created.ok
            accepted = await service.accept_request(42)
            assert accepted.ok
            assert json.loads(requests_path.read_text(encoding="utf-8")) == {}
            assert json.loads(teams_path.read_text(encoding="utf-8"))["42"]["team"] == "A LAMP"
            missing = await service.reject_request(42)
            assert not missing.ok
            await service.create_request(43, "Other Employee", "R LAMP")
            rejected = await service.reject_request(43)
            assert rejected.ok
            assert "43" not in json.loads(requests_path.read_text(encoding="utf-8"))

        asyncio.run(scenario())


if __name__ == "__main__":
    test_team_service()
    print("TEAM_SERVICE PASS")
