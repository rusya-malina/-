from __future__ import annotations

import asyncio
import hashlib
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from storage import replace_latest_file


async def replace_in_thread(source: Path, target: Path) -> None:
    await asyncio.to_thread(replace_latest_file, str(source), str(target))


async def run_round(directory: Path, prefix: str, workers: int = 40) -> tuple[bytes, set[str]]:
    target = directory / f"latest_{prefix}.xlsx"
    target.write_bytes(f"old-{prefix}".encode())
    sources = []
    for index in range(workers):
        source = directory / f".{prefix}_{index}.xlsx"
        source.write_bytes(f"{prefix}-new-{index}".encode())
        sources.append(source)

    results = await asyncio.gather(
        *(replace_in_thread(source, target) for source in sources),
        return_exceptions=True,
    )
    errors = {repr(result) for result in results if isinstance(result, Exception)}
    assert not errors, f"concurrent replacement errors: {errors}"
    assert target.exists(), f"missing latest file: {target}"
    remaining_sources = {path.name for path in sources if path.exists()}
    assert not remaining_sources, f"temporary files remain: {remaining_sources}"
    content = target.read_bytes()
    allowed = {f"{prefix}-new-{index}".encode() for index in range(workers)}
    assert content in allowed, f"target contains unexpected content: {content!r}"
    return content, {hashlib.sha256(content).hexdigest()}


async def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        directory = Path(temp_dir)
        kpi_content, _ = await run_round(directory, "kpi", workers=40)
        issuance_content, _ = await run_round(directory, "issuance", workers=40)
        assert (directory / "latest_kpi.xlsx").exists()
        assert (directory / "latest_issuance.xlsx").exists()
        assert kpi_content.startswith(b"kpi-new-")
        assert issuance_content.startswith(b"issuance-new-")
        leftovers = list(directory.glob(".*.xlsx"))
        assert leftovers == [], f"hidden temporary files remain: {leftovers}"
    print("concurrent latest-file tests passed: 40 KPI + 40 issuance replacements")


if __name__ == "__main__":
    asyncio.run(main())
