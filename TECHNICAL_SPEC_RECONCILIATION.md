# Техническое задание: автоматическая сверка Excel, users и groups

**Версия:** 1.0  
**Статус:** Draft for implementation  
**Проект:** Telegram-бот управления KPI, выдачами и сотрудниками  
**Репозиторий:** `rusya-malina/-`, ветка `main`  
**Целевой runtime:** Python 3.12, `python-telegram-bot 22.8`, JSON storage  

## 1. Назначение документа

Документ описывает реализацию автоматической сверки между KPI Excel-файлом, `users.json`, `groups.json`, `kpi_data.json` и, при необходимости, `issuance_data.json`. Основная цель — исключить повторение ситуаций, когда сотрудник отсутствует в последнем Excel, но отображается в списке пользователей, либо когда зарегистрированный Telegram-пользователь заменяется временной Excel-записью.

> **Ключевой принцип:** Excel описывает KPI-снимок, но не имеет права самостоятельно удалять или изменять реального Telegram-пользователя. Реальные пользователи идентифицируются числовым Telegram ID и всегда имеют приоритет над synthetic Excel-записями.

## 2. Контекст и исходная проблема

В текущей модели временные сотрудники из Excel могут создаваться с ключами вида `excel_<normalized_name>`. Такие записи нужны для отображения сотрудников из KPI-файла, у которых ещё нет Telegram-регистрации. Проблема возникает, когда temporary Excel record остаётся после изменения файла или когда реальная регистрация появляется после создания synthetic-записи.

Были выявлены два характерных сценария:

| Сценарий | Нежелательное поведение | Требуемое поведение |
|---|---|---|
| Светлана Борухова отсутствует в последнем Excel | Старая запись `excel_борухова светлана` остаётся в users registry | Synthetic-запись удаляется после подтверждения нового Excel; реальный Telegram ID сохраняется |
| Александра Умарова зарегистрирована после появления Excel-записи | В registry остаётся synthetic-запись вместо реального Telegram ID | При approval реальный Telegram ID заменяет synthetic key, а KPI и group данные сохраняются |

Текущая архитектура уже содержит application services и atomic JSON transactions. Новая функция должна продолжить эту архитектуру и не возвращать запись напрямую из Telegram handlers в JSON storage.

## 3. Цели и нецели

### 3.1. Цели

Необходимо реализовать единый reconciliation pipeline, который:

1. читает Excel и строит валидированный snapshot;
2. сопоставляет строки Excel с реальными Telegram users и synthetic Excel users;
3. отдельно выявляет добавления, обновления, удаления, конфликты и неподтверждённые соответствия;
4. показывает администратору полный preview до записи;
5. применяет изменения одной атомарной операцией;
6. никогда не удаляет числовой Telegram user ID только потому, что его нет в Excel;
7. автоматически объединяет synthetic Excel record с реальным Telegram user при approval;
8. сохраняет аудит операции и позволяет откатить последний подтверждённый импорт;
9. предоставляет отчёт о расхождениях координатору или администратору.

### 3.2. Нецели

В рамках первой версии не требуется заменить JSON storage на SQL, менять формат Telegram UI целиком, автоматически разрешать неоднозначные совпадения ФИО или удалять историю выдач. Все неоднозначные случаи должны попадать в ручной review.

## 4. Источники данных и приоритеты

### 4.1. Классификация источников

| Источник | Назначение | Идентификатор | Приоритет |
|---|---|---|---:|
| `users.json` | Реестр пользователей | числовой Telegram ID или `excel_*` | 1 |
| `groups.json` | Группа пользователя | тот же ID, что в users | 1 |
| `kpi_data.json` | KPI snapshot | normalized employee name | 2 |
| `issuance_data.json` | Выдачи и история | Telegram ID или legacy synthetic ID | 2 |
| KPI Excel | Новый KPI snapshot | `full_name` и KPI columns | 3 |
| Registration request | Подтверждение реального Telegram identity | Telegram ID из pending key | 0 при approval |

### 4.2. Правила приоритета

Реальный Telegram ID имеет приоритет над любым Excel-derived key. Registration approval имеет приоритет над текущим synthetic record. Excel может обновлять KPI, создавать временного сотрудника и удалять устаревшего synthetic сотрудника, но не может удалять реального Telegram user.

Если Excel и Telegram содержат разные варианты имени, числовой Telegram ID сохраняется, а изменение имени попадает в раздел `name_changes` и требует либо автоматического безопасного обновления, либо ручного подтверждения согласно настройке администратора.

## 5. Каноническая модель reconciliation

Необходимо добавить внутренние модели в `domain/models.py` или отдельный модуль `domain/reconciliation.py`.

```python
class RecordSource(StrEnum):
    TELEGRAM = "telegram"
    EXCEL = "excel"
    MERGED = "merged"

class ReconciliationStatus(StrEnum):
    MATCHED = "matched"
    NEW_EXCEL = "new_excel"
    STALE_EXCEL = "stale_excel"
    TELEGRAM_ONLY = "telegram_only"
    NAME_CHANGED = "name_changed"
    CONFLICT = "conflict"
    INVALID = "invalid"

@dataclass(frozen=True)
class ReconciliationIssue:
    status: ReconciliationStatus
    employee_name: str
    user_id: str | None = None
    candidate_ids: tuple[str, ...] = ()
    message_key: str = ""
    severity: str = "info"

@dataclass(frozen=True)
class ReconciliationPlan:
    operation_id: str
    source_file: str
    source_sha256: str
    rows_total: int
    valid_rows: int
    additions: tuple[dict, ...]
    updates: tuple[dict, ...]
    stale_synthetic: tuple[dict, ...]
    protected_telegram_only: tuple[dict, ...]
    conflicts: tuple[ReconciliationIssue, ...]
    invalid_rows: tuple[ReconciliationIssue, ...]
```

Каждая операция получает `operation_id` в формате UUID и SHA-256 исходного Excel-файла. Все последующие действия — preview, confirm, apply, rollback — должны ссылаться на этот идентификатор.

## 6. Нормализация и сопоставление

### 6.1. Нормализация ФИО

Для первичного сравнения используется единая функция:

```python
def normalize_person_name(value: object) -> str:
    return re.sub(r"\\s+", " ", str(value or "").strip().casefold())
```

В первой версии запрещается автоматически переставлять части имени, исправлять опечатки или применять fuzzy matching без отдельного статуса `CONFLICT`. Например, `Светлана Борухова` и `Борухова Светлана` считаются разными исходными строками, но могут быть показаны администратору как потенциальный конфликт.

### 6.2. Приоритет сопоставления

Сопоставление выполняется в следующем порядке:

1. точное совпадение числового Telegram ID, если ID присутствует в служебном mapping или в подтверждённой заявке;
2. точное нормализованное совпадение имени с реальным user (`user_id.isdigit()`);
3. точное нормализованное совпадение с synthetic `excel_*` user;
4. обнаружение перестановки слов как `CONFLICT`, без автоматического удаления;
5. fuzzy candidate только для ручного review, без автоматической записи.

### 6.3. Защита реальных пользователей

Любой ключ, состоящий только из цифр, считается реальным Telegram ID. При KPI import запрещено:

- удалять такой ключ из `users.json`;
- заменять его synthetic key;
- удалять его group record только из-за отсутствия имени в Excel;
- удалять связанные выдачи;
- считать его незарегистрированным.

Удалению после подтверждения подлежат только записи с ключом `excel_*`, если их normalized name отсутствует в новом валидном Excel snapshot и запись не была преобразована в Telegram record.

## 7. Алгоритм сверки Excel

### 7.1. Этап A — чтение и валидация

Сервис `application/reconciliation_service.py` получает путь к `.xlsx`, вычисляет SHA-256 и читает лист KPI. Проверяются:

- расширение `.xlsx`;
- наличие обязательной колонки `full_name`;
- наличие всех KPI columns;
- отсутствие пустых или `NaN` names;
- неотрицательные и конечные числовые значения;
- отсутствие дублей normalized names в одном файле;
- отсутствие строк, в которых `full_name` совпадает с `nan`, `none` или пустой строкой.

Неверные строки не должны silently пропускаться. Они попадают в `invalid_rows` с номером Excel-строки и причиной.

### 7.2. Этап B — построение индексов

Строятся следующие индексы:

```text
telegram_users_by_id:      numeric user_id -> user record
telegram_users_by_name:    normalized name -> list[numeric user_id]
synthetic_users_by_name:   normalized name -> list[excel_* key]
groups_by_id:               user_id -> group record
kpi_by_name:                normalized name -> KPI record
excel_rows_by_name:         normalized name -> Excel row
```

Если один normalized name связан с несколькими числовыми Telegram IDs, создаётся `CONFLICT`, и автоматическое обновление такого имени запрещается.

### 7.3. Этап C — вычисление плана

Для каждого Excel row:

- при совпадении с одним реальным Telegram user создаётся `MATCHED` или `NAME_CHANGED`;
- при совпадении с одним synthetic user создаётся `MATCHED_SYNTHETIC`;
- при отсутствии записи создаётся `NEW_EXCEL` с key `excel_<normalized_name>`;
- при нескольких кандидатах создаётся `CONFLICT`;
- при invalid row создаётся `INVALID`.

Для каждого synthetic user, отсутствующего в `excel_rows_by_name`, создаётся `STALE_EXCEL`. Для каждого числового Telegram ID, отсутствующего в Excel, создаётся `TELEGRAM_ONLY` со статусом `protected`.

## 8. Особые правила для случаев Боруховой и Умаровой

### 8.1. Светлана Борухова

Если в текущем registry существует:

```text
excel_борухова светлана -> Борухова Светлана
```

а в новом Excel отсутствует normalized name `борухова светлана`, план должен содержать:

```text
status: STALE_EXCEL
action: DELETE_SYNTHETIC
```

Если одновременно существует реальный user `1272226234 -> Светлана Борухова`, он должен иметь статус `TELEGRAM_ONLY` или `MATCHED` и сохраняться.

### 8.2. Александра Умарова

Если в registry существует:

```text
excel_александра умарова -> Александра Умарова
```

и приходит registration approval для Telegram ID `896915843`, `RegistrationService` должен атомарно:

1. удалить synthetic key из `users.json`;
2. создать/обновить `users[896915843]`;
3. перенести group record с synthetic key на `896915843`;
4. перенести issuance record с synthetic key на `896915843`, если он существует;
5. оставить `kpi_data[александра умарова]` без изменения;
6. записать `migrated_aliases` в OperationResult и audit log.

## 9. Preview и пользовательский сценарий

### 9.1. Запуск

Администратор открывает `Загрузить данные KPI` и отправляет `.xlsx`. Бот не меняет JSON сразу.

### 9.2. Preview

В preview отображаются:

```text
Строк в файле: N
Валидных строк: N
Новых Excel-записей: N
Обновлений реальных пользователей: N
Устаревших synthetic-записей к удалению: N
Реальных Telegram-пользователей, защищённых от удаления: N
Изменений имён: N
Конфликтов: N
Ошибок строк: N
```

Preview должен содержать отдельные списки:

- `Будет добавлено`;
- `Будет обновлено`;
- `Будет удалено только как synthetic Excel`;
- `Будет сохранено как Telegram-only`;
- `Требует решения администратора`;
- `Ошибки Excel`.

Кнопки:

```text
✅ Подтвердить импорт
⚠️ Подтвердить только безопасные изменения
📄 Скачать отчёт сверки
❌ Отменить
```

Если есть `CONFLICT`, обычная кнопка полного подтверждения должна быть недоступна. Администратор может применить только безопасные изменения, оставив конфликтные строки без записи.

### 9.3. Повторный просмотр

Для каждого staged operation preview должен сохраняться в transient state или operation file до подтверждения. Нельзя применять staged operation, если SHA-256 файла, operation owner или срок действия preview не совпадают.

## 10. Применение и атомарность

`ReconciliationService.apply(plan)` должен использовать `JsonTransaction` с упорядоченными lock paths. Минимальный набор файлов для KPI import:

```text
users.json
 groups.json
kpi_data.json
issuance_data.json — только если выполняется migration synthetic issuance
reconciliation_operations.json
```

При ошибке ни один из файлов не должен остаться в промежуточном состоянии. Перед apply создаётся backup всех затрагиваемых файлов. В operation log сохраняются SHA-256 backup-файлов.

### 10.1. Безопасные изменения

Разрешены автоматически:

- создание новой synthetic Excel-записи;
- обновление KPI существующего реального пользователя по однозначному имени;
- обновление KPI существующего synthetic пользователя;
- удаление stale synthetic user;
- перенос synthetic record на подтверждённый Telegram ID;
- сохранение Telegram-only user без изменений.

### 10.2. Изменения, требующие review

Требуют ручного решения:

- два Telegram IDs с одинаковым ФИО;
- один Telegram ID, потенциально связанный с двумя ФИО;
- перестановка имени и фамилии без точного совпадения;
- изменение имени реального пользователя;
- Excel row с отрицательными, бесконечными или нечисловыми значениями;
- попытка заменить реальный Telegram ID synthetic key.

## 11. Rollback

Для каждой подтверждённой операции хранится:

```json
{
  "operation_id": "uuid",
  "created_at": "ISO-8601",
  "actor_id": "telegram-id",
  "source_file": "latest_kpi.xlsx",
  "source_sha256": "sha256",
  "status": "applied",
  "backup_dir": "backups/<operation_id>/",
  "rows_total": 20,
  "added": 0,
  "updated": 18,
  "deleted_synthetic": 1,
  "protected_telegram": 2,
  "conflicts": 0
}
```

Администратор должен иметь кнопку `↩️ Откатить последний импорт`. Откат доступен только для последней операции, если после неё не было другой операции, изменившей те же файлы. Перед rollback создаётся новый backup текущего состояния.

## 12. Изменения в коде

Необходимо добавить:

```text
application/reconciliation_service.py
application/reconciliation_models.py или domain/reconciliation.py
repositories/reconciliation_repository.py — при необходимости
presentation/handlers/reconciliation.py — после стабилизации service
```

Необходимо изменить:

```text
application/import_service.py
application/registration_service.py
handlers/uploads.py
handlers/requests.py — только для отображения operation result
data_models.py — при добавлении source/operation fields
config.py — пути operation log и reconciliation backups
```

### 12.1. Требуемые методы service

```python
class ReconciliationService:
    async def build_plan(self, source_path: str, actor_id: int) -> ReconciliationPlan: ...
    async def apply_safe(self, plan: ReconciliationPlan) -> OperationResult: ...
    async def apply_all(self, plan: ReconciliationPlan) -> OperationResult: ...
    async def rollback(self, operation_id: str, actor_id: int) -> OperationResult: ...
    async def get_operation(self, operation_id: str) -> dict | None: ...
    async def list_open_conflicts(self) -> list[ReconciliationIssue]: ...
```

`ImportService` должен делегировать reconciliation policy в `ReconciliationService`, а не самостоятельно решать, какие записи удалять. Это предотвращает расхождение правил между KPI import, issuance import и registration approval.

## 13. UI для администратора и координатора

Администратор получает полный reconciliation report. Координатор получает только read-only отчёт по своей зоне ответственности: новые сотрудники, отсутствующие в Excel, конфликты имён и незарегистрированные записи.

В списке пользователей необходимо показывать источник записи:

```text
✅ Telegram — Светлана Борухова — R LAMP
✅ Telegram — Александра Умарова — R LAMP
⚠️ Excel — Новый сотрудник без Telegram — A LAMP
```

Внутри callback нельзя передавать длинное или неэкранированное ФИО. Для операций следует использовать `operation_id`, `user_id` и безопасные внутренние keys. ФИО отображается только из server-side staged plan.

## 14. Audit и наблюдаемость

Каждая операция должна логировать:

- actor Telegram ID;
- operation ID;
- исходный файл и SHA-256;
- количество строк;
- количество валидных и invalid rows;
- additions, updates, stale synthetic, protected Telegram-only;
- conflicts;
- результат apply или rollback;
- список migrated aliases без публикации персональных данных в обычный application log.

В application logs ФИО следует маскировать или сокращать до безопасного вида. Полный reconciliation report хранится в ограниченном JSON operation log и доступен только администратору.

## 15. Тестирование

### 15.1. Unit tests

Необходимо покрыть:

1. нормализацию пробелов и регистра;
2. exact matching real Telegram user;
3. exact matching synthetic Excel user;
4. stale synthetic deletion;
5. protection of numeric Telegram IDs;
6. empty/NaN names;
7. duplicate normalized names;
8. name permutation conflict;
9. registration promotion synthetic→Telegram;
10. migration of groups and issuance;
11. idempotent repeated apply;
12. rollback after apply.

### 15.2. Contract tests

Contract test должен воспроизводить минимум два обязательных сценария:

```text
Scenario A: latest Excel does not contain Борухова Светлана.
Expected: excel_борухова светлана is deleted; numeric Telegram record is protected.

Scenario B: Excel contains Александра Умарова, then registration approval arrives for 896915843.
Expected: excel_александра умарова is replaced by 896915843; group/KPI/issuance are preserved.
```

### 15.3. Integration tests

Тест должен создать временные `users.json`, `groups.json`, `kpi_data.json`, `issuance_data.json`, применить plan и проверить:

- atomicity при искусственной ошибке записи;
- отсутствие частично применённого состояния;
- корректность operation log;
- корректность rollback;
- отсутствие изменений production files.

### 15.4. Regression checklist

После каждого изменения запускаются:

```text
python3 tools/test_architecture_contract.py
python3 tools/test_permissions.py
python3 tools/test_rewrite_contracts.py
python3 tools/test_import_service.py
python3 tools/test_excel_preview.py
python3 tools/test_unified_employee_reports.py
python3 tools/test_registration_approval_consistency.py
python3 tools/data_audit.py
ruff check .
python3 -m compileall -q .
pip3 check
```

## 16. Нефункциональные требования

| Требование | Критерий |
|---|---|
| Безопасность данных | Ни один apply без preview и backup |
| Атомарность | Нет partial writes при ошибке |
| Производительность | До 1 000 Excel rows обрабатываются без блокировки event loop; pandas выполняется через `asyncio.to_thread` |
| Повторяемость | Повторный apply того же SHA-256 не создаёт дубли |
| Идемпотентность | Повторный approval не создаёт второй user record |
| Наблюдаемость | Каждая операция имеет operation ID и status |
| Откат | Последний успешный import можно отменить |
| Совместимость | Existing KPI/import/registration flows продолжают проходить regression suite |
| Доступ | Полный report доступен только admin; coordinator получает read-only subset |

## 17. Критерии приёмки

Функция считается принятой, если выполнены все условия:

1. При Excel import устаревшая запись `excel_борухова светлана` удаляется после подтверждения нового файла.
2. Числовой Telegram user Светланы `1272226234` не удаляется, даже если её нет в Excel.
3. Реальный Telegram user Александры `896915843` сохраняется при последующих KPI imports.
4. Approval Александры заменяет synthetic record и переносит её group/issuance данные.
5. Пустые и `NaN` строки Excel не создают пользователей.
6. Конфликты ФИО не применяются автоматически.
7. Preview показывает additions, updates, stale synthetic, protected users, conflicts и invalid rows.
8. Apply создаёт backup и operation log.
9. Rollback восстанавливает состояние до операции.
10. Повторный apply является идемпотентным.
11. Все текущие regression tests остаются зелёными.
12. `data_audit.py` подтверждает `invalid=0` и отсутствие synthetic records, которые должны быть удалены.
13. Production health endpoint остаётся доступным после deploy.

## 18. Этапы реализации

### Этап 1 — Domain policy и plan builder

Вынести нормализацию, статусы, индексы и reconciliation plan в pure Python modules. Добавить unit tests без Telegram runtime.

### Этап 2 — Preview adapter

Подключить plan builder к staged Excel upload. Не менять текущие JSON write paths. Добавить новый preview с безопасными категориями.

### Этап 3 — Atomic apply и operation log

Перевести подтверждение Excel import на `ReconciliationService.apply_safe`. Добавить backup, operation ID и rollback.

### Этап 4 — Registration promotion

Связать `RegistrationService` с reconciliation identity policy. Approval реального Telegram ID должен поглощать synthetic alias и переносить связанные records.

### Этап 5 — Production rollout

Создать backup рабочих JSON, выполнить shadow validation на копии, запустить полный CI, выполнить deploy, проверить health и вручную проверить две контрольные записи.

## 19. Definition of Done

Работа считается завершённой, когда технические критерии приёмки выполнены в CI, два контрольных сценария Боруховой и Умаровой проходят на временном snapshot, production deploy имеет статус `live`, operation log содержит тестовую операцию, а администратор видит в preview, какие записи будут защищены, добавлены, обновлены или удалены.
