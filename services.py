"""Общие расчёты, уведомления и фоновые задания."""
from telegram.error import TelegramError

from bot_context import (
    ContextTypes,
    ReplyKeyboardRemove,
    datetime,
    logging,
    math,
    pd,
    re,
    timezone,
)
from config import (
    ADMIN_ID,
    GROUPS_FILE,
    USERS_FILE,
)
from data_models import user_name as get_user_name
from storage import load_json, load_pending


async def check_pending_requests_job(context: ContextTypes.DEFAULT_TYPE):
    pending = await load_pending()
    count = len(pending)
    if not count:
        return

    now = datetime.now(timezone.utc)
    last_reminder = context.application.bot_data.get("last_requests_reminder")
    if last_reminder:
        try:
            if (now - datetime.fromisoformat(last_reminder)).total_seconds() < 1800:
                return
        except (TypeError, ValueError):
            pass

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"⏰ **Напоминание:** у вас есть необработанные заявки (`{count} шт.`).\n"
                "Откройте раздел: **⚙️ Дополнительно ➡️ 📥 Заявки**."
            ),
            parse_mode="Markdown",
        )
        context.application.bot_data["last_requests_reminder"] = now.isoformat()
    except TelegramError as e:
        logging.error(f"Не удалось отправить напоминание о заявках: {e}")


def find_telegram_user_ids_by_name(users: dict, target_name: str) -> list[int]:
    """Находит Telegram ID только по полному имени, без учета группы пользователя."""
    clean_target = _normalize_person_name(target_name)
    result = []
    for user_id, user_record in users.items():
        if not str(user_id).isdigit():
            continue
        if _normalize_person_name(get_user_name(user_record)) == clean_target:
            result.append(int(user_id))
    return result


async def notify_users_kpi_updated(context: ContextTypes.DEFAULT_TYPE, target_names: list[str]) -> dict[str, int]:
    """Notify every real Telegram user represented in an applied KPI snapshot."""
    try:
        users = await load_json(USERS_FILE)
    except (OSError, TypeError, ValueError) as error:
        logging.exception("Не удалось загрузить users.json для KPI notifications: %s", error)
        return {"sent": 0, "failed": 0, "unmatched": len(target_names)}

    recipients: dict[int, str] = {}
    unmatched = 0
    for target_name in dict.fromkeys(str(name).strip() for name in target_names if str(name).strip()):
        target_user_ids = find_telegram_user_ids_by_name(users, target_name)
        if not target_user_ids:
            unmatched += 1
        for target_user_id in target_user_ids:
            recipients[target_user_id] = target_name

    sent = 0
    failed = 0
    for target_user_id, target_name in recipients.items():
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    f"🔔 **{target_name}**, ваши показатели KPI были обновлены!\n\n"
                    "Нажмите кнопку **«Мой KPI»**, чтобы посмотреть актуальные данные."
                ),
                parse_mode="Markdown",
            )
            sent += 1
        except TelegramError as error:
            failed += 1
            logging.error("Не удалось отправить KPI notification пользователю %s: %s", target_user_id, error)

    logging.info(
        "KPI notifications completed: recipients=%s sent=%s failed=%s unmatched=%s",
        len(recipients),
        sent,
        failed,
        unmatched,
    )
    return {"sent": sent, "failed": failed, "unmatched": unmatched}


async def notify_user_kpi_updated(context: ContextTypes.DEFAULT_TYPE, target_name: str):
    """Backward-compatible single-user notification wrapper."""
    return await notify_users_kpi_updated(context, [target_name])


async def notify_managers_team_kpi_recalculated(context: ContextTypes.DEFAULT_TYPE) -> dict[str, int]:
    """Notify registered coor/SPV/MNG users after a team KPI recalculation."""
    try:
        users = await load_json(USERS_FILE)
        groups = await load_json(GROUPS_FILE)
    except (OSError, TypeError, ValueError) as error:
        logging.exception("Не удалось загрузить users/groups для KPI manager notification: %s", error)
        return {"sent": 0, "failed": 0, "unmatched": 0}

    management_groups = {"coor A", "coor R", "SPV", "MNG"}
    recipients: dict[int, tuple[str, str]] = {}
    for user_id, user_record in users.items():
        if not str(user_id).isdigit():
            continue
        group_record = groups.get(str(user_id), {})
        group = ""
        if isinstance(group_record, dict):
            group = str(group_record.get("group") or group_record.get("team") or "").strip()
        if not group and isinstance(user_record, dict):
            group = str(user_record.get("group") or user_record.get("team") or "").strip()
        if group in management_groups:
            name = (
                str(user_record.get("name") or user_record.get("full_name") or "Руководитель")
                if isinstance(user_record, dict)
                else "Руководитель"
            )
            recipients[int(user_id)] = (name, group)

    sent = 0
    failed = 0
    for manager_id, (name, group) in recipients.items():
        try:
            await context.bot.send_message(
                chat_id=manager_id,
                text=(
                    "🔔 **Загружен новый файл KPI.**\n\n"
                    f"{name}, ваши командные показатели были перерасчитаны для группы **{group}**.\n\n"
                    "Откройте **«Мои KPI» → «KPI команды»**, чтобы посмотреть актуальные данные."
                ),
                parse_mode="Markdown",
            )
            sent += 1
        except TelegramError as error:
            failed += 1
            logging.error("Не удалось отправить manager KPI notification пользователю %s: %s", manager_id, error)

    logging.info(
        "Manager KPI notifications completed: recipients=%s sent=%s failed=%s",
        len(recipients),
        sent,
        failed,
    )
    return {"sent": sent, "failed": failed, "unmatched": 0}


async def notify_user_bot_stopped(context: ContextTypes.DEFAULT_TYPE, user_id: str):
    if user_id and user_id.isdigit():
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text="⛔️ Работа бота остановлена.\nВы были удалены из системы",
                reply_markup=ReplyKeyboardRemove(),
            )
        except TelegramError as e:
            logging.error(f"Не удалось отправить уведомление об остановке пользователю {user_id}: {e}")


def _format_quantity(value: float) -> str:
    value = float(value or 0)
    return f"{value:.0f}" if value.is_integer() else f"{value:.2f}".rstrip("0").rstrip(".")


def calculate_balances(user_kpi: dict, issuance_record: dict) -> dict:
    """Возвращает выданное, использованное и остаток по двум типам продукции."""
    mints_issued = float(issuance_record.get("mints_issued", 0) or 0)
    sticks_issued = float(issuance_record.get("sticks_issued", 0) or 0)
    las_done = float(user_kpi.get("micro_las_fact", 0) or 0)
    lau_done = float(user_kpi.get("micro_lau_fact", 0) or 0)
    gt_done = float(user_kpi.get("gt_fact", 0) or 0)
    microacts_done = las_done + lau_done
    return {
        "mints_issued": mints_issued,
        "mints_used": microacts_done,
        "mints_balance": mints_issued - microacts_done,
        "sticks_issued": sticks_issued,
        "sticks_used": gt_done,
        "sticks_balance": sticks_issued - gt_done,
        "las_done": las_done,
        "lau_done": lau_done,
    }


def _normalize_person_name(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _find_column(columns, aliases):
    normalized_columns = {_normalize_person_name(column).replace(" ", "_"): column for column in columns}
    for alias in aliases:
        normalized_alias = _normalize_person_name(alias).replace(" ", "_")
        if normalized_alias in normalized_columns:
            return normalized_columns[normalized_alias]
    return None


def _parse_nonnegative_quantity(value) -> float:
    if value is None:
        return 0.0
    try:
        if bool(pd.isna(value)):
            return 0.0
    except (TypeError, ValueError):
        pass
    number = float(str(value).strip().replace(",", "."))
    if not math.isfinite(number) or number < 0:
        raise ValueError("Количество должно быть конечным числом не меньше нуля")
    return number
