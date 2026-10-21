"""Helpers for replacing bot-generated reports in group chats."""

from __future__ import annotations

from contextlib import suppress
from typing import Any


async def replace_group_report(
    context: Any,
    *,
    chat_id: int,
    text: str,
    parse_mode: str | None = None,
) -> Any:
    """Delete the previous report from this group and send the fresh one."""
    bot_data = getattr(context, "bot_data", None)
    if not isinstance(bot_data, dict):
        bot_data = {}
        with suppress(Exception):
            context.bot_data = bot_data

    report_ids = bot_data.setdefault("group_report_message_ids", {})
    previous_message_id = report_ids.get(str(chat_id))
    if previous_message_id:
        with suppress(Exception):
            await context.bot.delete_message(chat_id=chat_id, message_id=int(previous_message_id))

    kwargs = {"chat_id": chat_id, "text": text}
    if parse_mode:
        kwargs["parse_mode"] = parse_mode
    message = await context.bot.send_message(**kwargs)
    report_ids[str(chat_id)] = message.message_id
    return message


__all__ = ["replace_group_report"]
