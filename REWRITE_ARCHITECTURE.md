# Целевая архитектура переписывания Telegram-бота

## Цель

Переписать бота по слоям без изменения пользовательской бизнес-логики, форматов рабочих JSON, текстов кнопок и callback-контрактов. Текущие handlers остаются baseline-реализацией до тех пор, пока новый слой не пройдёт shadow и regression validation.

## Правила границ

| Слой | Ответственность | Запрещено |
|---|---|---|
| `runtime/` | startup, health server, polling supervisor, signals, Render recovery | бизнес-правила пользователей и KPI |
| `application/` | use cases: регистрация, одобрение, KPI, выдача, импорт, отчёты | Telegram `Update`, `Message`, `CallbackQuery` |
| `domain/` | чистые модели, статусы, permissions, расчёты и invariants; единственные `Permission`/`Mode` contracts | JSON, Telegram API, GitHub API |
| `repositories/` | чтение/запись users, groups, requests, teams, KPI и issuance | форматирование Telegram-сообщений |
| `integrations/` | Telegram delivery, GitHub sync, Excel parser, Render health | прямые изменения domain state |
| `presentation/` | thin Telegram handlers, keyboards, navigation, response mapping | расчёты и multi-file persistence |
| `tests/` | contract, regression, property, data and shadow checks | изменение production data |

## Target tree

```text
bot.py                         # только composition root
runtime/
  polling_supervisor.py        # retry, Conflict recovery, graceful shutdown
  health_server.py             # / и /healthz
  startup.py                   # migrations, restore, dependency composition
application/
  registration_service.py
  employee_service.py
  kpi_service.py
  issuance_service.py
  team_service.py
  request_service.py
  import_service.py
  report_service.py
domain/
  models.py                    # immutable command/result records
  permissions.py               # role and mode policy
  invariants.py                # validation and business constraints
  calculations.py              # KPI/balance calculations
repositories/
  json_repository.py            # atomic JSON primitives
  employee_repository.py
  request_repository.py
  kpi_repository.py
  issuance_repository.py
  session_repository.py
integrations/
  telegram_gateway.py
  excel_gateway.py
  github_gateway.py
presentation/
  router.py                     # explicit route registry for user/coor/admin flows
  navigation.py
  keyboards.py
  handlers/
    user.py
    coor.py
    admin.py
    requests.py
    kpi.py
    issuance.py
    uploads.py
  responses.py
bot.py
```

## Use-case contract

Каждый application service принимает typed command и возвращает typed result. Он не знает о Telegram objects и не отправляет сообщения. Пример контракта:

```python
@dataclass(frozen=True)
class ApproveRegistrationCommand:
    request_id: str
    actor_id: int

@dataclass(frozen=True)
class OperationResult:
    ok: bool
    code: str
    message_key: str
    changed_ids: tuple[str, ...] = ()
```

Telegram handler только преобразует `Update` в command, проверяет route-level permission через policy, вызывает service и преобразует result в response. Все multi-file writes выполняются внутри repository transaction boundary.

## Состояние

Бизнес-состояние хранится в repositories и сохраняет текущие JSON filenames/schema v1/v2. Временное состояние Telegram conversation хранится отдельно в `FlowSession`; оно никогда не смешивается с users, groups, KPI или issuance. Admin/coor mode является session policy state и сохраняется через отдельный `session_repository`, а не через domain JSON.

## Permission policy

Проверка строится в три шага: идентичность Telegram ID, назначенная роль/группа и активный режим. `domain.models.Permission` и `domain.models.Mode` являются едиными contracts; текущий `permissions.py` только адаптирует их к Telegram context и session persistence. Handler не может сам решать, что пользователь является admin. `PermissionPolicy.require(actor, permission, mode)` возвращает typed denial либо разрешает use case. `/admin` и `/coor` являются командами смены режима, а не обходом permission checks.

## Navigation policy

Каждый flow имеет `return_target`: `USER_HOME`, `COOR_HOME`, `ADMIN_HOME`, `KPI_MENU`, `ISSUANCE_MENU`, `REQUESTS_MENU` или `CANCELLED`. Handler не строит главное меню вручную и не передаёт `admin_mode=True`; navigation service вычисляет меню из policy context. Любое завершение или исключение очищает только flow session и не сбрасывает permission state.

## Import policy

Excel flow состоит из пяти фаз: download, parse, validate, preview, apply. До `apply` repositories не вызываются. Preview содержит число строк, новые/изменённые записи, ошибки и агрегаты MINTS/стиков. Apply выполняет backup, ordered transaction, latest-file replacement и audit event. Cancel удаляет staging artifact.

## Migration strategy

Переписывание выполняется вертикальными срезами. На каждом срезе старый handler и новый service сравниваются на одинаковом snapshot данных. Только после совпадения результатов новый adapter становится активным. Рабочие JSON не меняются во время extraction и shadow validation; перед любой миграцией создаётся backup.

## Current migration status

The first vertical slice is active: registration approval mutations now run through `application/registration_service.py`, the unified employee registry is available through `application/employee_service.py`, `application/report_service.py` owns the active personal balances read path, `application/admin_service.py` owns users+KPI deletion, and `presentation/router.py` owns ConversationHandler composition. Runtime startup, health and polling are now isolated in `runtime/startup.py`, `runtime/health_server.py` and `runtime/polling_supervisor.py`; `bot.py` is only the composition root. Legacy handler functions remain as Telegram adapters until each remaining domain flow receives its own application service and shadow test.

## Acceptance criteria

1. Все текущие regression tests остаются зелёными.
2. Для каждого use case есть contract test без Telegram runtime.
3. Для admin/coor проверяется отсутствие cross-mode leakage.
4. Для Excel подтверждается отсутствие записи до preview confirmation.
5. Повторный Render wake не требует `/start` или `/admin`.
6. `data_audit.py` показывает нулевые schema-invalid records.
7. GitHub Actions и Render deploy проходят до переключения production route.
