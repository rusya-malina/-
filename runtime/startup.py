"""Deterministic startup stages for the bot process."""
from __future__ import annotations

from github_sync import restore_kpi_state_sync
from permissions import load_persisted_admin_mode
from storage import _migrate_team_label, _reset_issuance_if_legacy, migrate_json_schemas


def prepare_data() -> None:
    """Run local schema/team migrations before Application composition."""
    migrate_json_schemas()
    _reset_issuance_if_legacy()
    _migrate_team_label()
    load_persisted_admin_mode()


def restore_external_state() -> None:
    """Restore the latest externally synchronized KPI snapshot."""
    restore_kpi_state_sync()


__all__ = ["prepare_data", "restore_external_state"]
