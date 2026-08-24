from bot_context import (
    ADMIN_ID,
    GROUPS_WITH_BALANCES,
    GROUPS_WITH_HOURS,
    TEAM_OPTIONS,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from config import GROUPS_WITH_MY_TRAINING, GROUPS_WITH_PLAN, GROUPS_WITH_TRAINING
from organization import is_management_group
from permissions import is_admin_mode
from roles import get_user_group_sync

COORDINATOR_GROUPS = frozenset({"coor A", "coor R"})


def get_registration_group_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["A LAMP", "R LAMP"], ["coor A", "coor R"], ["SPV", "MNG"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_main_keyboard(user_id: int, group: str | None = None, admin_mode: bool = False) -> ReplyKeyboardMarkup:
    if user_id == ADMIN_ID and admin_mode:
        keyboard = [
            ["Новый расчет"],
            ["Мой KPI", "Справочник KPI"],
            ["Остатки"],
            ["📦 Выдача"],
            ["Загрузить данные"],
            ["📢 Рассылка", "⚙️ Дополнительно"],
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    group = group or get_user_group_sync(user_id)
    if is_management_group(group):
        keyboard = [["Моя команда"], ["Новый расчет"], ["Мой KPI", "Справочник KPI"]]
        if group in COORDINATOR_GROUPS:
            keyboard.append(["📦 Выдача"])
        if group in GROUPS_WITH_TRAINING:
            keyboard.append(["Загрузить обучение"])
        if group in GROUPS_WITH_BALANCES:
            keyboard.append(["Остатки"])
    elif group in GROUPS_WITH_HOURS or group in GROUPS_WITH_BALANCES:
        keyboard = [["Новый расчет"], ["Мой KPI", "Справочник KPI"], ["Остатки"]]
        if group in GROUPS_WITH_MY_TRAINING:
            keyboard.append(["Мои обучения"])
        if group in GROUPS_WITH_PLAN:
            keyboard.insert(0, ["📅 План"])
    elif group in TEAM_OPTIONS:
        keyboard = [["Новый расчет"], ["Мой KPI", "Справочник KPI"]]
        if group in GROUPS_WITH_PLAN:
            keyboard.insert(0, ["📅 План"])
    else:
        # Legacy users may predate group registration; keep them active without re-registration.
        keyboard = [["Новый расчет"], ["Мой KPI", "Справочник KPI"]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_context_keyboard(user_id: int, context, group: str | None = None) -> ReplyKeyboardMarkup:
    return get_main_keyboard(user_id, group, admin_mode=is_admin_mode(user_id, context))


def get_data_keyboard() -> ReplyKeyboardMarkup:
    """Единое меню загрузки KPI, Excel-выдач и статистики для администратора."""
    return ReplyKeyboardMarkup(
        [
            ["📥 Загрузить KPI (Excel)"],
            ["📥 Загрузить выдачи (Excel)"],
            ["📊 Выгрузка статистики"],
            ["⬅️ Назад"],
        ],
        resize_keyboard=True,
    )


def get_issuance_keyboard() -> ReplyKeyboardMarkup:
    """Меню ручной выдачи MINTS и стиков для администратора и координаторов."""
    return ReplyKeyboardMarkup(
        [
            ["MINTS"],
            ["Стики"],
            ["⬅️ Назад"],
        ],
        resize_keyboard=True,
    )


def get_kpi_menu_keyboard() -> ReplyKeyboardMarkup:
    """Backward-compatible alias for the unified data menu."""
    return get_data_keyboard()


def get_team_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["📊 KPI команды"], ["📦 Остатки команды"], ["⬅️ Назад"]],
        resize_keyboard=True,
    )


def get_extra_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["👥 Пользователи"], ["📥 Заявки"], ["🗑 Удалить по номеру"], ["⬅️ Назад"]],
        resize_keyboard=True,
    )




cancel_keyboard = ReplyKeyboardMarkup([["⬅️ Назад"]], resize_keyboard=True)


def get_team_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["A LAMP", "R LAMP"], ["coor A", "coor R"], ["SPV", "MNG"], ["⬅️ Назад"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_issuance_confirmation_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Выдать", callback_data="issue_confirm")],
            [InlineKeyboardButton("👤 Изменить пользователя", callback_data="issue_change_user")],
            [InlineKeyboardButton("❌ Отмена", callback_data="issue_cancel")],
        ]
    )
