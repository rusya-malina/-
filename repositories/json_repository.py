"""Repository boundary over the existing atomic JSON storage."""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from storage import load_json, update_json, update_many_json


@dataclass(frozen=True)
class JsonRepository:
    """Small application-facing adapter for one canonical JSON document."""

    path: str

    async def load(self) -> dict[str, Any]:
        return await load_json(self.path)

    async def update(self, mutator: Callable[[dict[str, Any]], Any]) -> Any:
        return await update_json(self.path, mutator)


@dataclass(frozen=True)
class JsonTransaction:
    """Ordered multi-document transaction boundary."""

    paths: tuple[str, ...]

    async def run(self, mutator: Callable[[dict[str, dict[str, Any]]], Any]) -> Any:
        return await update_many_json(self.paths, mutator)


def transaction(paths: Iterable[str]) -> JsonTransaction:
    """Build a deterministic transaction with de-duplicated paths."""
    return JsonTransaction(tuple(sorted(set(paths))))


__all__ = ["JsonRepository", "JsonTransaction", "transaction"]
