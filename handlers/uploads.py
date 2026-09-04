"""Тяжёлые операции с Excel, изолированные от меню и основного роутера."""
import re

from telegram.error import TelegramError

from application.import_service import ImportSafetyError, ImportService
from application.team_kpi_service import TeamKpiService
from bot_context import (
    ContextTypes,
    ConversationHandler,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    asyncio,
    logging,
    os,
    pd,
    tempfile,
)
from config import ADMIN_ID, GROUPS_FILE, TEAMS_FILE, UPLOADED_DATA_DIR, USERS_FILE
from errors import StorageError
from github_sync import sync_data_state, sync_kpi_state
from keyboards import cancel_keyboard, get_data_keyboard, get_issuance_keyboard
from navigation import clear_pending_import
from permissions import Permission, has_permission
from services import (
    _find_column,
    _normalize_person_name,
    _parse_nonnegative_quantity,
    notify_managers_team_kpi_recalculated,
    notify_users_kpi_updated,
)
from states import (
    ISSUANCE_EXCEL_UPLOAD,
    ISSUANCE_MENU,
    KPI_MENU_STATE,
    UPLOAD_EXCEL,
)
from storage import load_json

MANAGEMENT_GROUPS = frozenset({"coor A", "coor R", "SPV", "MNG"})
MANAGEMENT_LABELS = {
    "coor": "coor",
    "coor a": "coor A",
    "coor r": "coor R",
    "коор": "coor",
    "коор a": "coor A",
    "коор р": "coor R",
    "spv": "SPV",
    "mng": "MNG",
}


def _excel_preview_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Подтвердить импорт", callback_data="excel_confirm")],
            [InlineKeyboardButton("❌ Отменить", callback_data="excel_cancel")],
        ]
    )


def _text(value: object) -> str:
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value or "").strip()


def _management_group(value: object) -> str | None:
    normalized = _normalize_person_name(value)
    if not normalized:
        return None
    for marker, group in sorted(MANAGEMENT_LABELS.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"(?:^|[\s/()_\-]){re.escape(marker)}(?:$|[\s/()_\-])", normalized):
            return group
    return None


def _management_names(users: dict, groups: dict, teams: dict) -> dict[str, str]:
    names: dict[str, str] = {}
    for source in (users, groups, teams):
        for user_id, record in source.items():
            if not isinstance(record, dict):
                continue
            group = _management_group(record.get("group") or record.get("team") or record.get("role") or record.get("position"))
            if not group:
                continue
            user_record = users.get(str(user_id), record)
            name = _text(user_record.get("name") if isinstance(user_record, dict) else user_record)
            name = name or _text(record.get("name") or record.get("full_name"))
            if name:
                names[_normalize_person_name(name)] = group
    return names


def _group_column_name(columns) -> object | None:
    return _find_column(
        columns,
        ["group", "team", "group_name", "team_name", "role", "position", "группа", "команда", "уровень", "должность"],
    )


def _blocked_management_rows(frame, users: dict, groups: dict, teams: dict | None = None) -> list[str]:
    """Return human-readable Excel rows that contain management KPI entries."""
    name_column = _find_column(frame.columns, ["full_name", "name", "employee", "employee_name", "фио", "сотрудник"])
    group_column = _group_column_name(frame.columns)
    management_names = _management_names(users, groups, teams or {})
    blocked: list[str] = []

    for excel_row_number, (_, row) in enumerate(frame.iterrows(), start=2):
        employee_name = _text(row.get(name_column)) if name_column else ""
        explicit_group = _text(row.get(group_column)) if group_column else ""
        detected_group = _management_group(explicit_group)
        normalized_name = _normalize_person_name(employee_name)
        token_group = _management_group(normalized_name)
        matched_group = management_names.get(normalized_name) if employee_name else None
        group = detected_group or matched_group or token_group
        if group:
            label = employee_name or "без ФИО"
            blocked.append(f"строка {excel_row_number}: {label} ({group})")
    return blocked


async def start_excel_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, context, Permission.DATA_UPLOAD):
        await update.message.reply_text("⛔️ У вас нет доступа к этой команде.")
        return ConversationHandler.END

    await update.message.reply_text(
        "📊 **Загрузка данных KPI из Excel**\n\n"
        "Отправьте `.xlsx` файл со следующими столбцами:\n"
        "• `full_name`, `gt_plan`, `gt_fact`, `micro_plan`, `micro_las_fact`, `micro_lau_fact`, `retrafic_plan`, `retrafic_fact`, `office_hours`, `field_hours`",
        reply_markup=cancel_keyboard,
        parse_mode="Markdown",
    )
    return UPLOAD_EXCEL


async def process_excel_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document

    if not document.file_name.lower().endswith(".xlsx"):
        await update.message.reply_text(
            "⚠️ Пожалуйста, отправьте файл в формате Excel (`.xlsx`).",
            parse_mode="Markdown",
        )
        return UPLOAD_EXCEL

    file_path = None
    try:
        os.makedirs(UPLOADED_DATA_DIR, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".kpi_", suffix=".xlsx", dir=UPLOADED_DATA_DIR, delete=False) as temp_file:
            file_path = temp_file.name
        file = await context.bot.get_file(document.file_id)
        await file.download_to_drive(file_path)
    except (OSError, StorageError, TelegramError) as error:
        logging.exception("Не удалось скачать KPI Excel: %s", error)
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        await update.message.reply_text("❌ Не удалось скачать Excel-файл. Попробуйте отправить его ещё раз.")
        return UPLOAD_EXCEL

    try:
        # Асинхронное чтение Excel для избежания фризов бота
        def read_and_clean_excel(path):
            df = pd.read_excel(path)
            required_cols = [
                "full_name", "gt_plan", "gt_fact", "micro_plan",
                "micro_las_fact", "micro_lau_fact", "retrafic_plan",
                "retrafic_fact", "office_hours", "field_hours",
            ]
            if not all(col in df.columns for col in required_cols):
                return None

            # Заменяем NaN на 0 для числовых столбцов
            numeric_cols = [
                "gt_plan", "gt_fact", "micro_plan", "micro_las_fact",
                "micro_lau_fact", "retrafic_plan", "retrafic_fact",
                "office_hours", "field_hours",
            ]
            df[numeric_cols] = df[numeric_cols].fillna(0)
            return df

        df = await asyncio.to_thread(read_and_clean_excel, file_path)

        if df is None:
            await update.message.reply_text(
                "❌ **Ошибка структуры файла! Проверьте обязательные столбцы (включая office_hours и field_hours).**",
                parse_mode="Markdown",
            )
            if os.path.exists(file_path):
                os.remove(file_path)
            return UPLOAD_EXCEL

        users = await load_json(USERS_FILE)
        groups = await load_json(GROUPS_FILE)
        teams = await load_json(TEAMS_FILE)
        blocked_rows = _blocked_management_rows(df, users, groups, teams)
        if blocked_rows:
            if os.path.exists(file_path):
                os.remove(file_path)
            await update.message.reply_text(
                "⛔ **Импорт KPI заблокирован.** В Excel найдены строки руководителей "
                "(`coor A`, `coor R`, `SPV` или `MNG`).\n\n"
                + "\n".join(blocked_rows[:10])
                + ("\n…" if len(blocked_rows) > 10 else "")
                + "\n\nЗагрузите файл только с сотрудниками `A LAMP` и `R LAMP`.",
                parse_mode="Markdown",
            )
            return UPLOAD_EXCEL

        service = ImportService.from_default_storage()
        staged = await service.prepare_kpi_import(df.to_dict("records"))
        unresolved_team_names = staged.get("unresolved_team_names", [])
        if unresolved_team_names:
            if os.path.exists(file_path):
                os.remove(file_path)
            await update.message.reply_text(
                "⛔ **Импорт KPI заблокирован.** Не удалось определить команду для сотрудников:\n\n"
                + "\n".join(f"• {name}" for name in unresolved_team_names[:10])
                + ("\n…" if len(unresolved_team_names) > 10 else "")
                + "\n\nДобавьте колонку `group`/`team` со значением `A LAMP` или `R LAMP` "
                "либо сначала назначьте сотрудникам команду через администратора.",
                parse_mode="Markdown",
            )
            return UPLOAD_EXCEL
        staged["temp_path"] = file_path
        context.user_data["pending_excel_import"] = staged
        updated_names = staged["updated_names"]
        new_names = staged["new_names"]
        removed_names = staged.get("removed_names", [])
        stale_names = staged.get("stale_names", [])
        audit = staged.get("user_audit", {})
        if int(audit.get("after_count", 0)) < int(audit.get("before_count", 0)):
            if os.path.exists(file_path):
                os.remove(file_path)
            context.user_data.pop("pending_excel_import", None)
            await update.message.reply_text(
                "⛔ **Импорт остановлен:** количество зарегистрированных пользователей уменьшается. "
                "Данные не изменены.",
                parse_mode="Markdown",
            )
            return UPLOAD_EXCEL
        sample = ", ".join(updated_names[:8])
        if len(updated_names) > 8:
            sample += ", …"
        preview = (
            "🔎 **Предпросмотр импорта KPI**\n\n"
            f"Строк в файле: **{len(df)}**\n"
            f"Пользователей до импорта: **{audit.get('before_count', 0)}**\n"
            f"Пользователей после импорта: **{audit.get('after_count', 0)}**\n"
            f"Новых сотрудников: **{len(audit.get('new_names', new_names))}**\n"
            f"Пропавших сотрудников: **{len(audit.get('removed_names', removed_names))}**\n"
            f"Изменённых ФИО: **{len(audit.get('changed_names', []))}**\n"
            f"Существующих записей вне файла сохранено: **{len(stale_names)}**\n"
            f"Сотрудников в preview: **{len(updated_names)}**\n"
            f"Примеры: {sample or 'нет'}\n\n"
            "Данные ещё не записаны. Подтвердите импорт или отмените его."
        )
        await update.message.reply_text(preview, reply_markup=_excel_preview_markup(), parse_mode="Markdown")
        return UPLOAD_EXCEL

    except ImportSafetyError as error:
        logging.warning("KPI Excel blocked by management-row guard: %s", error)
        if os.path.exists(file_path):
            os.remove(file_path)
        await update.message.reply_text(
            "⛔ **Импорт KPI заблокирован.** В файле нельзя загружать KPI руководителей. "
            "Удалите строки `coor A`, `coor R`, `SPV` и `MNG`, затем отправьте Excel повторно.",
            parse_mode="Markdown",
        )
        return UPLOAD_EXCEL
    except (OSError, KeyError, StorageError, TypeError, ValueError, TelegramError) as e:
        logging.error(f"Ошибка при обработке Excel: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        await update.message.reply_text("❌ **Произошла ошибка при чтении файла.**")
        return UPLOAD_EXCEL


async def excel_preview_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not has_permission(query.from_user.id, context, Permission.DATA_UPLOAD):
        await query.message.edit_text("⛔️ У вас нет доступа к импорту.")
        return ConversationHandler.END

    staged = context.user_data.get("pending_excel_import")
    if not isinstance(staged, dict):
        await query.message.edit_text("ℹ️ Предпросмотр устарел. Загрузите файл заново.")
        return ConversationHandler.END

    if query.data == "excel_cancel":
        clear_pending_import(context)
        await query.message.edit_text("❌ Импорт отменён. Данные не изменены.")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="📥 Раздел загрузки данных:",
            reply_markup=get_data_keyboard() if staged.get("kind") == "kpi" else get_issuance_keyboard(),
        )
        return KPI_MENU_STATE if staged.get("kind") == "kpi" else ISSUANCE_MENU

    if query.data != "excel_confirm":
        return UPLOAD_EXCEL

    kind = staged.get("kind")
    try:
        if kind == "kpi":
            await _apply_kpi_import(staged, context)
            menu = get_data_keyboard()
            state = KPI_MENU_STATE
            text = "✅ Импорт KPI подтверждён и применён."
        elif kind == "issuance":
            await _apply_issuance_import(staged)
            menu = get_issuance_keyboard()
            state = ISSUANCE_MENU
            text = "✅ Импорт выдач подтверждён и применён."
        else:
            raise ValueError("Неизвестный тип staged Excel import")
    except ImportSafetyError:
        logging.exception("KPI import blocked by user-count safety guard")
        clear_pending_import(context)
        await query.message.edit_text(
            "⛔ Импорт KPI остановлен: количество зарегистрированных пользователей не должно уменьшаться. "
            "Данные не изменены."
        )
        return UPLOAD_EXCEL
    except (OSError, KeyError, StorageError, TypeError, ValueError, TelegramError) as error:
        logging.exception("Ошибка применения подтверждённого Excel import: %s", error)
        clear_pending_import(context)
        if kind == "issuance":
            if isinstance(error, StorageError):
                reason = "ошибка сохранения runtime-хранилища"
            elif isinstance(error, OSError):
                reason = "ошибка сохранения последнего Excel-файла"
            elif isinstance(error, (TypeError, ValueError, KeyError)):
                reason = "ошибка данных или сопоставления сотрудника"
            else:
                reason = "ошибка Telegram или файла"
            text = f"❌ Выдачи не применены: {reason}. Данные не изменены."
        else:
            text = "❌ Не удалось применить импорт. Данные не изменены или восстановлены."
        await query.message.edit_text(text)
        return ConversationHandler.END

    context.user_data.pop("pending_excel_import", None)
    await query.message.edit_text(text)
    await context.bot.send_message(chat_id=query.message.chat_id, text="📥 Раздел загрузки данных:", reply_markup=menu)
    return state


async def _apply_kpi_import(staged: dict, context: ContextTypes.DEFAULT_TYPE) -> None:
    source_path = staged["temp_path"]
    await sync_data_state()
    await ImportService.from_default_storage().apply_kpi_import(staged, source_path)
    staged["temp_path"] = None
    await TeamKpiService.from_default_storage().rebuild()
    await sync_kpi_state()
    await notify_users_kpi_updated(context, staged.get("updated_names", []))
    await notify_managers_team_kpi_recalculated(context)


async def _apply_issuance_import(staged: dict) -> None:
    source_path = staged["temp_path"]
    await ImportService.from_default_storage().apply_issuance_import(staged, source_path)
    staged["temp_path"] = None


async def process_issuance_excel_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, context, Permission.DATA_UPLOAD):
        await update.message.reply_text("⛔️ У вас нет доступа к этому разделу.")
        return ConversationHandler.END

    document = update.message.document
    if not document or not document.file_name.lower().endswith(".xlsx"):
        await update.message.reply_text("⚠️ Отправьте файл в формате `.xlsx` или нажмите «Назад».", parse_mode="Markdown")
        return ISSUANCE_EXCEL_UPLOAD

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="issuance_", suffix=".xlsx", delete=False) as temp_file:
            temp_path = temp_file.name
        remote_file = await context.bot.get_file(document.file_id)
        await remote_file.download_to_drive(temp_path)

        def read_issuance_excel(path):
            frame = pd.read_excel(path, dtype=object)
            name_column = _find_column(
                frame.columns,
                ["full_name", "name", "employee", "employee_name", "фио", "фио сотрудника", "сотрудник", "имя", "имя сотрудника"],
            )
            mints_column = _find_column(
                frame.columns,
                ["mints", "mints_issued", "mint", "минтс", "минты", "выданные_mints", "выдано_mints", "выданные минтс"],
            )
            sticks_column = _find_column(
                frame.columns,
                ["sticks", "sticks_issued", "stick", "стики", "выданные_стики", "выдано_стиков"],
            )
            if not name_column or not mints_column or not sticks_column:
                return None, None
            return frame, (name_column, mints_column, sticks_column)

        frame, columns = await asyncio.to_thread(read_issuance_excel, temp_path)
        if frame is None:
            await update.message.reply_text(
                "❌ Не найдены обязательные колонки. Нужны: имя сотрудника, MINTS и Стики.",
                reply_markup=get_issuance_keyboard(),
            )
            return ISSUANCE_MENU

        name_column, mints_column, sticks_column = columns
        rows = []
        errors = []
        for excel_row_number, (_, row) in enumerate(frame.iterrows(), start=2):
            employee_name = str(row.get(name_column, "")).strip()
            if not employee_name or employee_name.lower() == "nan":
                continue
            try:
                mints_amount = _parse_nonnegative_quantity(row.get(mints_column, 0))
                sticks_amount = _parse_nonnegative_quantity(row.get(sticks_column, 0))
            except (TypeError, ValueError) as error:
                errors.append(f"строка {excel_row_number}: {error}")
                continue
            rows.append((employee_name, mints_amount, sticks_amount))

        if errors:
            preview = "\n".join(errors[:5])
            await update.message.reply_text(
                f"❌ Excel не загружен: найдены ошибки в данных.\n{preview}",
                reply_markup=get_issuance_keyboard(),
            )
            return ISSUANCE_MENU
        if not rows:
            await update.message.reply_text("❌ В Excel нет заполненных строк с сотрудниками.", reply_markup=get_issuance_keyboard())
            return ISSUANCE_MENU

        service = ImportService.from_default_storage()
        staged = await service.prepare_issuance_import(rows, ADMIN_ID)
        staged["temp_path"] = temp_path
        context.user_data["pending_excel_import"] = staged
        added_without_telegram = staged["added_without_telegram"]
        temp_path = None
        preview = (
            "🔎 **Предпросмотр импорта выдач**\n\n"
            f"Строк в файле: **{len(rows)}**\n"
            f"MINTS к добавлению: **{sum(item[1] for item in rows):.2f}**\n"
            f"Стиков к добавлению: **{sum(item[2] for item in rows):.2f}**\n"
            f"Новых записей без Telegram ID: **{len(added_without_telegram)}**\n\n"
            "Данные ещё не записаны. Подтвердите импорт или отмените его."
        )
        await update.message.reply_text(preview, reply_markup=_excel_preview_markup(), parse_mode="Markdown")
        return ISSUANCE_EXCEL_UPLOAD
    except (OSError, KeyError, StorageError, TypeError, ValueError, TelegramError) as error:
        logging.exception("Ошибка загрузки Excel выдач: %s", error)
        await update.message.reply_text("❌ Не удалось обработать Excel-файл. Проверьте формат и попробуйте снова.", reply_markup=get_issuance_keyboard())
        return ISSUANCE_MENU
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
