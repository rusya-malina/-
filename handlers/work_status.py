"""Daily work status and same-team pairing workflow."""

from __future__ import annotations

import logging
from contextlib import suppress
from datetime import datetime
from zoneinfo import ZoneInfo

from application.work_status_service import (
    accept_pair_invite,
    create_pair_invite,
    get_coordinator_overview,
    get_pair_candidates,
    get_today_status,
    get_work_status_recipients,
    reject_pair_invite,
    set_work_status,
)
from bot_context import ContextTypes, InlineKeyboardButton, InlineKeyboardMarkup, Update
from config import BOT_TIMEZONE
from roles import get_user_group

STATUS_BUTTON = "📍 Статус работы"
TEAM_GROUPS = frozenset({"A LAMP", "R LAMP"})
COORDINATOR_GROUPS = frozenset({"coor A", "coor R"})
logger = logging.getLogger(__name__)


def _today() -> str:
    return datetime.now(ZoneInfo(BOT_TIMEZONE)).date().isoformat()


def _status_markup(user_id: str, status: dict) -> InlineKeyboardMarkup:
    if status.get("pair_name"):
        return InlineKeyboardMarkup(
            [[InlineKeyboardButton(f"👯 В паре с {status['pair_name']}", callback_data="work_status:noop")]]
        )
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🟢 Работаю", callback_data="work_status:set:working")],
            [InlineKeyboardButton("🔴 Не работаю", callback_data="work_status:set:not_working")],
        ]
    )


def _candidate_markup(candidates: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"👯 {item['name']}", callback_data=f"work_status:invite:{item['user_id']}")]
        for item in candidates
    ]
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="work_status:menu")])
    return InlineKeyboardMarkup(rows)


def _invite_markup(invite_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Принять", callback_data=f"work_status:accept:{invite_id}")],
            [InlineKeyboardButton("❌ Отказать", callback_data=f"work_status:reject:{invite_id}")],
        ]
    )


def _daily_poll_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Да, работаю", callback_data="work_status:set:working")],
            [InlineKeyboardButton("❌ Нет, не работаю", callback_data="work_status:set:not_working")],
        ]
    )


async def send_work_status_poll_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask every A/R LAMP employee whether they work today at 15:00."""
    recipients = await get_work_status_recipients()
    for employee in recipients:
        user_id = str(employee["user_id"])
        current_status = await get_today_status(user_id)
        if current_status.get("status") in {"working", "not_working"}:
            logger.info("Опрос статуса пропущен: сотрудник %s уже проголосовал", user_id)
            continue
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text="Вы работаете сегодня?",
                reply_markup=_daily_poll_markup(),
            )
        except Exception:  # noqa: BLE001
            logger.exception("Не удалось отправить опрос статуса сотруднику %s", user_id)


def _format_overview(overview: dict) -> str:
    lines = [f"📍 **Статус работы на {overview['date']}**", ""]
    pairs = overview["pairs"]
    lines.append("👯 **Пары**")
    if pairs:
        for pair in pairs:
            lines.append(f"• {pair['first_name']} + {pair['second_name']}")
    else:
        lines.append("• Нет подтверждённых пар")

    lines.extend(["", "🟢 **Работают без пары**"])
    if overview["working"]:
        lines.extend(f"• {item['name']} ({item['group']})" for item in overview["working"])
    else:
        lines.append("• Нет")

    lines.extend(["", "🔴 **Не работают**"])
    if overview["not_working"]:
        lines.extend(f"• {item['name']} ({item['group']})" for item in overview["not_working"])
    else:
        lines.append("• Нет")
    return "\n".join(lines)


async def show_work_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    group = await get_user_group(user_id)
    if group not in TEAM_GROUPS | COORDINATOR_GROUPS:
        await update.message.reply_text("⚠️ Статус работы доступен только сотрудникам A/R и координаторам.")
        return

    if group in COORDINATOR_GROUPS:
        overview = await get_coordinator_overview()
        await update.message.reply_text(_format_overview(overview), parse_mode="Markdown")
        return

    status = await get_today_status(user_id)
    if status.get("pair_name"):
        text = f"📍 **Ваш статус на {_today()}:**\n👯 Вы в паре с *{status['pair_name']}*."
    elif status.get("status") == "working":
        text = f"📍 **Ваш статус на {_today()}:** 🟢 Работаю\n\nВыберите коллегу в пару:"
        candidates = await get_pair_candidates(user_id)
        if not candidates:
            text += "\n\nПока нет других работающих коллег без пары."
            await update.message.reply_text(text, parse_mode="Markdown")
            return
        await update.message.reply_text(text, reply_markup=_candidate_markup(candidates), parse_mode="Markdown")
        return
    elif status.get("status") == "not_working":
        text = f"📍 **Ваш статус на {_today()}:** 🔴 Не работаю"
    else:
        text = f"📍 **Статус работы на {_today()}**\n\nВыберите статус:"

    await update.message.reply_text(text, reply_markup=_status_markup(user_id, status), parse_mode="Markdown")


async def show_working_lists(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the combined A/R LAMP work-status lists for coordinators."""
    user_id = str(update.effective_user.id)
    group = await get_user_group(user_id)
    if group not in COORDINATOR_GROUPS:
        await update.message.reply_text("⚠️ Списки работающих доступны только координаторам A/R.")
        return
    overview = await get_coordinator_overview()
    await update.message.reply_text(_format_overview(overview), parse_mode="Markdown")


async def work_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    data = query.data or ""
    group = await get_user_group(user_id)

    if data == "work_status:noop":
        status = await get_today_status(user_id)
        text = f"👯 Сегодня вы в паре с *{status.get('pair_name', 'коллегой')}*."
        await query.message.edit_text(text, parse_mode="Markdown")
        return

    if data == "work_status:menu":
        status = await get_today_status(user_id)
        if group in COORDINATOR_GROUPS:
            await query.message.edit_text(_format_overview(await get_coordinator_overview()), parse_mode="Markdown")
            return
        if status.get("pair_name"):
            await query.message.edit_text(f"👯 Сегодня вы в паре с *{status['pair_name']}*.", parse_mode="Markdown")
            return
        await query.message.edit_text(
            f"📍 **Статус работы на {_today()}**\n\nВыберите статус:",
            reply_markup=_status_markup(user_id, status),
            parse_mode="Markdown",
        )
        return

    if data.startswith("work_status:set:"):
        desired = data.rsplit(":", 1)[1]
        if desired not in {"working", "not_working"}:
            return
        result = await set_work_status(user_id, desired)
        if not result["ok"]:
            await query.message.edit_text(result["message"], parse_mode="Markdown")
            return
        if desired == "not_working":
            await query.message.edit_text(f"🔴 **Статус на {_today()}: Не работаю**", parse_mode="Markdown")
            return
        candidates = await get_pair_candidates(user_id)
        if candidates:
            await query.message.edit_text(
                f"🟢 **Статус на {_today()}: Работаю**\n\nВыберите коллегу в пару:",
                reply_markup=_candidate_markup(candidates),
                parse_mode="Markdown",
            )
        else:
            await query.message.edit_text(
                f"🟢 **Статус на {_today()}: Работаю**\n\nПока нет других работающих коллег без пары.",
                parse_mode="Markdown",
            )
        return

    if data.startswith("work_status:invite:"):
        target_id = data.rsplit(":", 1)[1]
        result = await create_pair_invite(user_id, target_id)
        if not result["ok"]:
            await query.message.edit_text(result["message"], parse_mode="Markdown")
            return
        try:
            await context.bot.send_message(
                chat_id=int(target_id),
                text=f"👯 *{result['sender_name']}* приглашает Вас в пару на {_today()}.",
                reply_markup=_invite_markup(result["invite_id"]),
                parse_mode="Markdown",
            )
        except Exception:  # noqa: BLE001
            await reject_pair_invite(result["invite_id"], reason="notification_failed")
            await query.message.edit_text(
                "⚠️ Не удалось отправить приглашение коллеге. Попробуйте снова.",
                parse_mode="Markdown",
            )
            return
        await query.message.edit_text(
            f"📨 Приглашение *{result['target_name']}* отправлено.\nОжидаем ответ.",
            parse_mode="Markdown",
        )
        return

    if data.startswith("work_status:accept:"):
        invite_id = data.rsplit(":", 1)[1]
        result = await accept_pair_invite(invite_id, user_id)
        await query.message.edit_text(result["message"], parse_mode="Markdown")
        if result["ok"]:
            with suppress(Exception):
                await context.bot.send_message(
                    chat_id=int(result["sender_id"]),
                    text=f"✅ *{result['receiver_name']}* приняла приглашение.\n👯 Вы в паре на {_today()}.",
                    parse_mode="Markdown",
                )
        return

    if data.startswith("work_status:reject:"):
        invite_id = data.rsplit(":", 1)[1]
        result = await reject_pair_invite(invite_id, reason="user_rejected")
        candidates = await get_pair_candidates(user_id)
        text = result["message"]
        if candidates:
            text += "\n\nВыберите другого коллегу:"
            await query.message.edit_text(text, reply_markup=_candidate_markup(candidates), parse_mode="Markdown")
        else:
            await query.message.edit_text(text, parse_mode="Markdown")
        if result.get("sender_id"):
            try:
                sender_id = str(result["sender_id"])
                sender_candidates = await get_pair_candidates(sender_id)
                sender_text = f"ℹ️ *{result['receiver_name']}* отказалась от приглашения в пару."
                if sender_candidates:
                    sender_text += "\n\nВыберите другого коллегу:"
                    await context.bot.send_message(
                        chat_id=int(sender_id),
                        text=sender_text,
                        reply_markup=_candidate_markup(sender_candidates),
                        parse_mode="Markdown",
                    )
                else:
                    await context.bot.send_message(
                        chat_id=int(sender_id),
                        text=sender_text,
                        parse_mode="Markdown",
                    )
            except Exception:  # noqa: BLE001
                pass
        return
