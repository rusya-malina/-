"""Pure application configuration and domain constants."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ADMIN_ID = 14599689
BASE_DIR = Path(os.getenv("BOT_DATA_DIR", ".")).expanduser()

USERS_FILE = str(BASE_DIR / "users.json")
KPI_FILE = str(BASE_DIR / "kpi_data.json")
PLANS_FILE = str(BASE_DIR / "plans_config.json")
PENDING_FILE = str(BASE_DIR / "pending_requests.json")
TEAM_REQUESTS_FILE = str(BASE_DIR / "team_requests.json")
USER_REQUESTS_FILE = str(BASE_DIR / "user_requests.json")
GROUPS_FILE = str(BASE_DIR / "groups.json")
REGISTRATION_DRAFTS_FILE = str(BASE_DIR / "registration_drafts.json")
DELETED_USERS_FILE = str(BASE_DIR / "deleted_users.json")
TEAMS_FILE = str(BASE_DIR / "teams.json")
ISSUANCE_FILE = str(BASE_DIR / "issuance_data.json")
ISSUANCE_SCHEMA_VERSION = 2
UPLOADED_DATA_DIR = str(BASE_DIR / "uploaded_data")
LATEST_KPI_FILE = os.path.join(UPLOADED_DATA_DIR, "latest_kpi.xlsx")
LATEST_ISSUANCE_FILE = os.path.join(UPLOADED_DATA_DIR, "latest_issuance.xlsx")
TRAINING_ONE_FILE = os.path.join(UPLOADED_DATA_DIR, "training_one.xlsx")
TRAINING_TWO_FILE = os.path.join(UPLOADED_DATA_DIR, "training_two.xlsx")
TRAINING_HISTORY_FILE = str(BASE_DIR / "training_history.json")
BOT_TIMEZONE = os.getenv("BOT_TIMEZONE", "Asia/Almaty")

TEAM_OPTIONS = ("A LAMP", "R LAMP", "coor A", "coor R", "SPV", "MNG")
GROUPS_WITH_BALANCES = frozenset({"A LAMP", "R LAMP", "coor A", "coor R"})
GROUPS_WITH_HOURS = frozenset({"A LAMP", "R LAMP"})
GROUPS_WITH_PLAN = frozenset({"A LAMP", "R LAMP"})
GROUPS_WITH_TRAINING = frozenset({"coor A", "coor R"})
GROUPS_WITH_MY_TRAINING = frozenset({"A LAMP", "R LAMP"})

ADMIN_SESSION_FILE = str(BASE_DIR / "admin_session.json")
