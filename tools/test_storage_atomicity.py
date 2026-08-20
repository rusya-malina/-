from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from storage import load_json, update_json


async def main() -> None:
    with tempfile.TemporaryDirectory(prefix="storage_atomicity_") as temp_dir:
        path = str(Path(temp_dir) / "counter.json")
        await update_json(path, lambda data: data.update({"count": 0}))

        async def increment() -> None:
            def mutate(data: dict) -> None:
                data["count"] = int(data.get("count", 0)) + 1

            await update_json(path, mutate)

        await asyncio.gather(*(increment() for _ in range(100)))
        result = await load_json(path)
        assert result == {"count": 100}, result
        assert json.loads(Path(path).read_text(encoding="utf-8")) == {"count": 100}

    print("STORAGE_ATOMICITY PASS")


if __name__ == "__main__":
    asyncio.run(main())
