"""Pure domain contracts used by the rewritten application layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Mode(StrEnum):
    ADMIN = "admin"
    COOR = "coor"


class Permission(StrEnum):
    ADMIN_PANEL = "admin_panel"
    USER_MANAGEMENT = "user_management"
    REGISTRATION_REQUESTS = "registration_requests"
    TEAM_APPROVAL = "team_approval"
    DATA_UPLOAD = "data_upload"
    BROADCAST = "broadcast"
    ISSUANCE = "issuance"
    KPI_MANAGEMENT = "kpi_management"


@dataclass(frozen=True)
class Actor:
    telegram_id: int
    group: str | None = None
    mode: Mode = Mode.COOR


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    permission: Permission
    reason: str = ""


@dataclass
class FlowSession:
    """Transient UI state; never persisted into business JSON documents."""

    flow: str | None = None
    return_target: str = "USER_HOME"
    values: dict[str, Any] = field(default_factory=dict)

    def clear(self) -> None:
        self.flow = None
        self.return_target = "USER_HOME"
        self.values.clear()


@dataclass(frozen=True)
class OperationResult:
    ok: bool
    code: str
    message_key: str
    changed_ids: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "Actor",
    "FlowSession",
    "Mode",
    "OperationResult",
    "Permission",
    "PermissionDecision",
]
