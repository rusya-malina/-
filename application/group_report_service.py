"""Helpers for replacing bot-generated reports in group chats."""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any

logger = logging.getLogger(__name__)


async def replace_group_report(
    context: Any,
    *,
    chat_id: int,
    report_type: str,
    text: str,
    parse_mode: str | None = None,
) -> Any:
    """Delete the previous report of this type and send the fresh one."""
    bot_data = getattr(context, "bot_data", None)
    if not isinstance(bot_data, dict):
        bot_data = {}
        with suppress(Exception):
            context.bot_data = bot_data

    report_ids = bot_data.setdefault("group_report_message_ids", {})
    report_key = f"{chat_id}:{report_type}"
    previous_message_id = report_ids.get(report_key)
    if previous_message_id:
        with suppress(Exception):
            await context.bot.delete_message(chat_id=chat_id, message_id=int(previous_message_id))

    kwargs = {"chat_id": chat_id, "text": text}
    if parse_mode:
        kwargs["parse_mode"] = parse_mode
    message = await context.bot.send_message(**kwargs)
    report_ids[report_key] = message.message_id
    return message


async def refresh_existing_group_reports(
    context: Any,
    *,
    report_type: str,
    text: str,
    parse_mode: str | None = None,
) -> int:
    """Refresh only already registered reports of one type in all groups.

    Report IDs are kept separately by ``chat_id:report_type``. Consequently,
    refreshing ``work_status`` cannot delete or replace a ``bookings`` report.
    If no report of this type has been sent in the current bot process, this
    function is a no-op; it never creates an unsolicited group message.
    """
    bot_data = getattr(context, "bot_data", None)
    if not isinstance(bot_data, dict):
        return 0
    report_ids = bot_data.get("group_report_message_ids")
    if not isinstance(report_ids, dict):
        return 0

    report_suffix = f":{report_type}"
    report_keys = [key for key in report_ids if str(key).endswith(report_suffix)]
    refreshed = 0
    for report_key in report_keys:
        try:
            chat_id = int(str(report_key)[: -len(report_suffix)])
            await replace_group_report(
                context,
                chat_id=chat_id,
                report_type=report_type,
                text=text,
                parse_mode=parse_mode,
            )
            refreshed += 1
        except Exception:  # noqa: BLE001
            logger.exception("Не удалось обновить групповой отчёт %s для %s", report_type, report_key)
    return refreshed


__all__ = ["refresh_existing_group_reports", "replace_group_report"]
