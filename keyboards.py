"""Клавиатуры и callback-разметка меню."""
from bot_context import (
    ADMIN_ID,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    TEAM_OPTIONS,
)


def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    keyboard = [
        ["Новый расчет"],
        ["Мой KPI", "Справочник KPI"],
        ["Остатки"],
        ["Определить команду"],
    ]
    if user_id == ADMIN_ID:
        keyboard.append(["Загрузить данные"])
        keyboard.append(["Выдача"])
        keyboard.append(["📢 Рассылка", "⚙️ Дополнительно"])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_kpi_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["📥 Загрузить KPI (Excel)", "✏️ Ввести KPI вручную"], ["⬅️ Назад"]],
        resize_keyboard=True,
    )


def get_extra_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["👥 Пользователи"], ["📥 Заявки на вступление"], ["🗑 Удалить по номеру"], ["⬅️ Назад"]],
        resize_keyboard=True,
    )


def get_issuance_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["MINTS", "Стики"], ["📥 Загрузить выдачи (Excel)"], ["📊 Выгрузка статистики"], ["⬅️ Назад"]],
        resize_keyboard=True,
    )


cancel_keyboard = ReplyKeyboardMarkup([["⬅️ Назад"]], resize_keyboard=True)


def get_team_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["A LAMP", "К LAMP"], ["coor A", "coor R"], ["SPV", "MNG"], ["⬅️ Назад"]],
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
