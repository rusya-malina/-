from bot_context import (
    ADMIN_ID,
    GROUPS_WITH_BALANCES,
    GROUPS_WITH_HOURS,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    TEAM_OPTIONS,
)
from roles import get_user_group_sync
from organization import is_management_group


def get_registration_group_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["A LAMP", "R LAMP"], ["coor A", "coor R"], ["SPV", "MNG"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_main_keyboard(user_id: int, group: str | None = None) -> ReplyKeyboardMarkup:
    if user_id == ADMIN_ID:
        keyboard = [
            ["Новый расчет"],
            ["Мой KPI", "Справочник KPI"],
            ["Остатки"],
            ["Загрузить данные"],
            ["📢 Рассылка", "⚙️ Дополнительно"],
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    group = group or get_user_group_sync(user_id)
    if is_management_group(group):
        keyboard = [["Моя команда"], ["Новый расчет"], ["Мой KPI", "Справочник KPI"]]
        if group in GROUPS_WITH_BALANCES:
            keyboard.append(["Остатки"])
        keyboard.append(["📝 Оставить заявку"])
    elif group in GROUPS_WITH_HOURS:
        keyboard = [["Новый расчет"], ["Мой KPI", "Справочник KPI"], ["Остатки"], ["📝 Оставить заявку"]]
    elif group in GROUPS_WITH_BALANCES:
        keyboard = [["Новый расчет"], ["Мой KPI", "Справочник KPI"], ["Остатки"], ["📝 Оставить заявку"]]
    elif group in TEAM_OPTIONS:
        keyboard = [["Новый расчет"], ["Мой KPI", "Справочник KPI"], ["📝 Оставить заявку"]]
    else:
        # Legacy users may predate group registration; keep them active without re-registration.
        keyboard = [["Новый расчет"], ["Мой KPI", "Справочник KPI"], ["📝 Оставить заявку"]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_data_keyboard() -> ReplyKeyboardMarkup:
    """Единое меню загрузки KPI, выдач и статистики для администратора."""
    return ReplyKeyboardMarkup(
        [
            ["📥 Загрузить KPI (Excel)"],
            ["MINTS", "Стики"],
            ["📥 Загрузить выдачи (Excel)"],
            ["📊 Выгрузка статистики"],
            ["⬅️ Назад"],
        ],
        resize_keyboard=True,
    )


def get_kpi_menu_keyboard() -> ReplyKeyboardMarkup:
    """Backward-compatible alias for the unified data menu."""
    return get_data_keyboard()


def get_extra_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["👥 Пользователи"], ["📥 Заявки"], ["🗑 Удалить по номеру"], ["⬅️ Назад"]],
        resize_keyboard=True,
    )


def get_issuance_keyboard() -> ReplyKeyboardMarkup:
    """Backward-compatible alias for the unified data menu."""
    return get_data_keyboard()


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
