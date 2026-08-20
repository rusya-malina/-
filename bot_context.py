"""Backward-compatible imports for legacy modules and tests.

New production code should import configuration from :mod:`config`, states from
:mod:`states`, and Telegram classes from python-telegram-bot directly.
"""

from __future__ import annotations

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
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest
from telegram.warnings import PTBUserWarning

from config import (
    ADMIN_ID,
    BASE_DIR,
    GROUPS_FILE,
    GROUPS_WITH_BALANCES,
    GROUPS_WITH_HOURS,
    ISSUANCE_FILE,
    ISSUANCE_SCHEMA_VERSION,
    KPI_FILE,
    LATEST_ISSUANCE_FILE,
    LATEST_KPI_FILE,
    PENDING_FILE,
    PLANS_FILE,
    REGISTRATION_DRAFTS_FILE,
    TEAM_OPTIONS,
    TEAM_REQUESTS_FILE,
    TEAMS_FILE,
    UPLOADED_DATA_DIR,
    USER_REQUESTS_FILE,
    USERS_FILE,
)
from states import (
    BROADCAST,
    CHANGE_LAST_NAME,
    CHANGE_NAME,
    CONFIRM_DELETE_EMP,
    DELETE_BY_NUM_STATE,
    EXTRA_MENU_STATE,
    ISSUANCE_AMOUNT,
    ISSUANCE_EXCEL_UPLOAD,
    ISSUANCE_MENU,
    ISSUANCE_USER,
    KPI_MENU_STATE,
    LAS,
    LAU,
    MANUAL_KPI_FIELD_HOURS,
    MANUAL_KPI_GT_FACT,
    MANUAL_KPI_MICRO_LAS_FACT,
    MANUAL_KPI_MICRO_LAU_FACT,
    MANUAL_KPI_NAME,
    MANUAL_KPI_NEW_NAME,
    MANUAL_KPI_OFFICE_HOURS,
    MANUAL_KPI_RETRAFIC_FACT,
    PENDING_REQUESTS_STATE,
    REG_FIRST_NAME,
    REG_GROUP,
    REG_LAST_NAME,
    SELECT_PREVIOUS_EMP,
    SET_PLAN_GT,
    SET_PLAN_MICRO,
    SET_PLAN_RETRAFIC,
    TEAM_MENU_STATE,
    TEAM_SELECTION,
    UPLOAD_EXCEL,
    USER_REQUEST,
)

warnings.filterwarnings("ignore", category=PTBUserWarning)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)

__all__ = [
    "ADMIN_ID",
    "BASE_DIR",
    "BROADCAST",
    "CHANGE_LAST_NAME",
    "CHANGE_NAME",
    "CONFIRM_DELETE_EMP",
    "DELETE_BY_NUM_STATE",
    "EXTRA_MENU_STATE",
    "GROUPS_FILE",
    "GROUPS_WITH_BALANCES",
    "GROUPS_WITH_HOURS",
    "ISSUANCE_AMOUNT",
    "ISSUANCE_EXCEL_UPLOAD",
    "ISSUANCE_FILE",
    "ISSUANCE_MENU",
    "ISSUANCE_SCHEMA_VERSION",
    "ISSUANCE_USER",
    "KPI_FILE",
    "KPI_MENU_STATE",
    "LAS",
    "LATEST_ISSUANCE_FILE",
    "LATEST_KPI_FILE",
    "LAU",
    "MANUAL_KPI_FIELD_HOURS",
    "MANUAL_KPI_GT_FACT",
    "MANUAL_KPI_MICRO_LAS_FACT",
    "MANUAL_KPI_MICRO_LAU_FACT",
    "MANUAL_KPI_NAME",
    "MANUAL_KPI_NEW_NAME",
    "MANUAL_KPI_OFFICE_HOURS",
    "MANUAL_KPI_RETRAFIC_FACT",
    "PENDING_FILE",
    "PENDING_REQUESTS_STATE",
    "PLANS_FILE",
    "REGISTRATION_DRAFTS_FILE",
    "REG_FIRST_NAME",
    "REG_GROUP",
    "REG_LAST_NAME",
    "SELECT_PREVIOUS_EMP",
    "SET_PLAN_GT",
    "SET_PLAN_MICRO",
    "SET_PLAN_RETRAFIC",
    "TEAMS_FILE",
    "TEAM_MENU_STATE",
    "TEAM_OPTIONS",
    "TEAM_REQUESTS_FILE",
    "TEAM_SELECTION",
    "UPLOADED_DATA_DIR",
    "UPLOAD_EXCEL",
    "USERS_FILE",
    "USER_REQUEST",
    "USER_REQUESTS_FILE",
    "Application",
    "BadRequest",
    "BaseHTTPRequestHandler",
    "CallbackQueryHandler",
    "CommandHandler",
    "ContextTypes",
    "ConversationHandler",
    "HTTPXRequest",
    "InlineKeyboardButton",
    "InlineKeyboardMarkup",
    "MessageHandler",
    "ReplyKeyboardMarkup",
    "ReplyKeyboardRemove",
    "ThreadingHTTPServer",
    "Update",
    "asyncio",
    "datetime",
    "filters",
    "json",
    "logging",
    "math",
    "os",
    "pd",
    "re",
    "tempfile",
    "threading",
    "timezone",
    "warnings",
]
