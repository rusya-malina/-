"""Pure application configuration and domain constants."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ADMIN_ID = 14599689

USERS_FILE = "users.json"
KPI_FILE = "kpi_data.json"
PLANS_FILE = "plans_config.json"
PENDING_FILE = "pending_requests.json"
TEAM_REQUESTS_FILE = "team_requests.json"
USER_REQUESTS_FILE = "user_requests.json"
GROUPS_FILE = "groups.json"
REGISTRATION_DRAFTS_FILE = "registration_drafts.json"
TEAMS_FILE = "teams.json"
ISSUANCE_FILE = "issuance_data.json"
ISSUANCE_SCHEMA_VERSION = 2
UPLOADED_DATA_DIR = "uploaded_data"
LATEST_KPI_FILE = os.path.join(UPLOADED_DATA_DIR, "latest_kpi.xlsx")
LATEST_ISSUANCE_FILE = os.path.join(UPLOADED_DATA_DIR, "latest_issuance.xlsx")

TEAM_OPTIONS = ("A LAMP", "R LAMP", "coor A", "coor R", "SPV", "MNG")
GROUPS_WITH_BALANCES = frozenset({"A LAMP", "R LAMP", "coor A", "coor R"})
GROUPS_WITH_HOURS = frozenset({"A LAMP", "R LAMP"})

BASE_DIR = Path(os.getenv("BOT_DATA_DIR", ".")).expanduser()
