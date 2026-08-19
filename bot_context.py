"""Общие настройки и зависимости. Бизнес-обработчики сюда не импортируются."""
import asyncio
import json
import logging
import math
import os
import re
import tempfile
import threading
import warnings
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pandas as pd
from dotenv import load_dotenv
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.error import BadRequest
from telegram.warnings import PTBUserWarning
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from telegram.request import HTTPXRequest

load_dotenv()
warnings.filterwarnings("ignore", category=PTBUserWarning)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)

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

(
    REG_GROUP,
    REG_FIRST_NAME,
    REG_LAST_NAME,
    LAS,
    LAU,
    CHANGE_NAME,
    CHANGE_LAST_NAME,
    BROADCAST,
    UPLOAD_EXCEL,
    MANUAL_KPI_NAME,
    SELECT_PREVIOUS_EMP,
    MANUAL_KPI_NEW_NAME,
    MANUAL_KPI_GT_FACT,
    MANUAL_KPI_MICRO_LAS_FACT,
    MANUAL_KPI_MICRO_LAU_FACT,
    MANUAL_KPI_RETRAFIC_FACT,
    MANUAL_KPI_OFFICE_HOURS,
    MANUAL_KPI_FIELD_HOURS,
    SET_PLAN_GT,
    SET_PLAN_MICRO,
    SET_PLAN_RETRAFIC,
    CONFIRM_DELETE_EMP,
    EXTRA_MENU_STATE,
    DELETE_BY_NUM_STATE,
    KPI_MENU_STATE,
    PENDING_REQUESTS_STATE,
    ISSUANCE_USER,
    ISSUANCE_AMOUNT,
    ISSUANCE_MENU,
    ISSUANCE_EXCEL_UPLOAD,
    TEAM_SELECTION,
    USER_REQUEST,
    TEAM_MENU_STATE,
) = range(33)

TEAM_OPTIONS = ("A LAMP", "R LAMP", "coor A", "coor R", "SPV", "MNG")
GROUPS_WITH_BALANCES = frozenset({"A LAMP", "R LAMP", "coor A", "coor R"})
GROUPS_WITH_HOURS = frozenset({"A LAMP", "R LAMP"})
