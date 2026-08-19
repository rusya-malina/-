"""Тяжёлые операции с Excel, изолированные от меню и основного роутера."""
from bot_context import *
from storage import load_json, save_json
from keyboards import cancel_keyboard, get_issuance_keyboard, get_main_keyboard
from services import (
    _find_column,
    _normalize_person_name,
    _parse_nonnegative_quantity,
    notify_user_kpi_updated,
)


async def start_excel_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
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
    user_id_num = update.effective_user.id
    document = update.message.document

    if not document.file_name.lower().endswith(".xlsx"):
        await update.message.reply_text(
            "⚠️ Пожалуйста, отправьте файл в формате Excel (`.xlsx`).",
            parse_mode="Markdown",
        )
        return UPLOAD_EXCEL

    file_path = "temp_kpi.xlsx"
    file = await context.bot.get_file(document.file_id)
    await file.download_to_drive(file_path)

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
                "office_hours", "field_hours"
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

        kpi_data = await load_json(KPI_FILE)
        users_data = await load_json(USERS_FILE)
        existing_user_names = [v.strip().lower() for v in users_data.values()]
        updated_names = []

        for _, row in df.iterrows():
            emp_name = str(row["full_name"]).strip()
            clean_name = emp_name.lower()
            
            kpi_data[clean_name] = {
                "original_name": emp_name,
                "gt_plan": float(row["gt_plan"]),
                "gt_fact": float(row["gt_fact"]),
                "micro_plan": float(row["micro_plan"]),
                "micro_las_fact": float(row["micro_las_fact"]),
                "micro_lau_fact": float(row["micro_lau_fact"]),
                "retrafic_plan": float(row["retrafic_plan"]),
                "retrafic_fact": float(row["retrafic_fact"]),
                "office_hours": float(row["office_hours"]),
                "field_hours": float(row["field_hours"]),
            }
            updated_names.append(emp_name)

            if clean_name not in existing_user_names:
                fake_uid = f"excel_{clean_name}"
                users_data[fake_uid] = emp_name
                existing_user_names.append(clean_name)

        await save_json(kpi_data, KPI_FILE)
        await save_json(users_data, USERS_FILE)
        if os.path.exists(file_path):
            os.remove(file_path)

        for name in updated_names:
            await notify_user_kpi_updated(context, name)

        await update.message.reply_text(
            f"✅ **Данные KPI успешно загружены!**\nЗаписей обновлено: `{len(df)}`",
            reply_markup=get_main_keyboard(user_id_num),
            parse_mode="Markdown",
        )
        return ConversationHandler.END

    except Exception as e:
        logging.error(f"Ошибка при обработке Excel: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        await update.message.reply_text("❌ **Произошла ошибка при чтении файла.**")
        return UPLOAD_EXCEL


async def process_issuance_excel_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
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
            name_column = _find_column(frame.columns, ["full_name", "name", "employee", "employee_name", "фио", "сотрудник", "имя"])
            mints_column = _find_column(frame.columns, ["mints", "mints_issued", "mint", "минтс", "минты", "выданные_mints", "выдано_mints"])
            sticks_column = _find_column(frame.columns, ["sticks", "sticks_issued", "stick", "стики", "выданные_стики", "выдано_стиков"])
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

        users_data = await load_json(USERS_FILE)
        issuance_data = await load_json(ISSUANCE_FILE)
        name_to_user_id = {
            _normalize_person_name(name): str(user_id)
            for user_id, name in users_data.items()
            if str(name).strip() and _normalize_person_name(name) != "nan"
        }
        added_without_telegram = []
        timestamp = datetime.now(timezone.utc).isoformat()
        for employee_name, mints_amount, sticks_amount in rows:
            normalized_name = _normalize_person_name(employee_name)
            user_id = name_to_user_id.get(normalized_name)
            if not user_id:
                user_id = f"excel_{normalized_name.replace(' ', '_')}"
                suffix = 2
                while user_id in users_data and _normalize_person_name(users_data[user_id]) != normalized_name:
                    user_id = f"excel_{normalized_name.replace(' ', '_')}_{suffix}"
                    suffix += 1
                users_data[user_id] = employee_name
                name_to_user_id[normalized_name] = user_id
                added_without_telegram.append(employee_name)

            record = issuance_data.setdefault(
                user_id,
                {"name": employee_name, "mints_issued": 0.0, "sticks_issued": 0.0, "history": []},
            )
            record["name"] = employee_name
            record.setdefault("mints_issued", 0.0)
            record.setdefault("sticks_issued", 0.0)
            record.setdefault("history", [])
            if mints_amount:
                record["mints_issued"] = float(record["mints_issued"]) + mints_amount
                record["history"].append({"type": "mints_excel", "amount": mints_amount, "admin_id": ADMIN_ID, "created_at": timestamp})
            if sticks_amount:
                record["sticks_issued"] = float(record["sticks_issued"]) + sticks_amount
                record["history"].append({"type": "sticks_excel", "amount": sticks_amount, "admin_id": ADMIN_ID, "created_at": timestamp})

        await save_json(users_data, USERS_FILE)
        await save_json(issuance_data, ISSUANCE_FILE)
        message = f"✅ Загружено строк: **{len(rows)}**. Выдачи добавлены сотрудникам по имени."
        if added_without_telegram:
            message += f"\nНовых записей без Telegram ID: **{len(added_without_telegram)}**."
        await update.message.reply_text(message, reply_markup=get_issuance_keyboard(), parse_mode="Markdown")
        return ISSUANCE_MENU
    except Exception as error:
        logging.exception("Ошибка загрузки Excel выдач: %s", error)
        await update.message.reply_text("❌ Не удалось обработать Excel-файл. Проверьте формат и попробуйте снова.", reply_markup=get_issuance_keyboard())
        return ISSUANCE_MENU
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
