"""Общие расчёты, уведомления и фоновые задания."""
from bot_context import *
from storage import load_json, load_pending


async def check_pending_requests_job(context: ContextTypes.DEFAULT_TYPE):
    pending = await load_pending()
    team_requests = await load_json(TEAM_REQUESTS_FILE)
    user_requests = await load_json(USER_REQUESTS_FILE)
    count = len(pending) + len(team_requests) + len(user_requests)
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
    except Exception as e:
        logging.error(f"Не удалось отправить напоминание о заявках: {e}")


async def notify_user_kpi_updated(context: ContextTypes.DEFAULT_TYPE, target_name: str):
    users = await load_json(USERS_FILE)
    clean_target = target_name.strip().lower()

    target_user_id = None
    for uid, u_name in users.items():
        if u_name.strip().lower() == clean_target:
            target_user_id = uid
            break

    if target_user_id and target_user_id.isdigit():
        try:
            await context.bot.send_message(
                chat_id=int(target_user_id),
                text=(
                    "🔔 **Ваши показатели KPI были обновлены!**\n\n"
                    "Нажмите кнопку **«Мой KPI»**, чтобы посмотреть актуальные данные."
                ),
                parse_mode="Markdown",
            )
        except Exception as e:
            logging.error(f"Не удалось отправить уведомление пользователю {target_user_id}: {e}")


async def notify_user_bot_stopped(context: ContextTypes.DEFAULT_TYPE, user_id: str):
    if user_id and user_id.isdigit():
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text="⛔️ Работа бота остановлена.\nВы были удалены из системы",
                reply_markup=ReplyKeyboardRemove(),
            )
        except Exception as e:
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
