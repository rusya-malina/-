"""Pure permission policy for the rewritten application layer."""
from __future__ import annotations

from config import ADMIN_ID
from domain.models import Actor, Mode, Permission, PermissionDecision

_ADMIN_PERMISSIONS = frozenset(Permission)


def is_admin_identity(telegram_id: int | str) -> bool:
    return str(telegram_id) == str(ADMIN_ID)


def decide(actor: Actor, permission: Permission) -> PermissionDecision:
    if not is_admin_identity(actor.telegram_id):
        return PermissionDecision(False, permission, "actor_is_not_admin")
    if actor.mode is not Mode.ADMIN:
        return PermissionDecision(False, permission, "admin_mode_is_not_active")
    if permission not in _ADMIN_PERMISSIONS:
        return PermissionDecision(False, permission, "permission_is_not_registered")
    return PermissionDecision(True, permission)


def require(actor: Actor, permission: Permission) -> None:
    decision = decide(actor, permission)
    if not decision.allowed:
        raise PermissionError(decision.reason)


__all__ = ["decide", "is_admin_identity", "require"]
