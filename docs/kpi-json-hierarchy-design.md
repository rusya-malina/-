# Проект JSON-структуры для иерархического KPI

## 1. Цель

Система должна загружать фактические KPI только для сотрудников команд `A LAMP` и `R LAMP`, а показатели руководителей рассчитывать автоматически на основании состава команд и исходных KPI сотрудников.

Иерархия:

```text
MNG
└── SPV
    ├── coor A
    │   └── A LAMP
    └── coor R
        └── R LAMP
```

Ключевой принцип: `users.json` хранит идентичность сотрудника, `groups.json` — принадлежность к организационной структуре, а `team_kpi_data.json` — только производные расчёты. KPI руководителя не должен импортироваться как независимая строка и не должен записываться в `users.json`.

## 2. Общие правила идентификации

1. Все идентификаторы хранятся как строки.
2. Реальный Telegram ID имеет вид строки из цифр и является основным идентификатором пользователя.
3. Excel-only запись может временно иметь ID вида `excel_<normalized_name>`. После сопоставления с Telegram ID она не должна превращаться в отдельного сотрудника: старый ID переносится в `aliases`.
4. Нормализованное ФИО используется только как поисковый ключ или fallback. Оно не заменяет стабильный Telegram ID.
5. Группа хранится в `groups.json`, а не дублируется как источник истины в `users.json`.
6. Удаление сотрудника из Excel не означает удаление из `users.json` или `groups.json`. Это должно быть отдельным подтверждённым административным действием.

## 3. users.json — единый реестр сотрудников

### 3.1. Назначение

`users.json` содержит одну запись на человека. Файл отвечает за идентичность, статус регистрации и технические aliases. Он не должен хранить текущий KPI и командные расчёты.

### 3.2. Рекомендуемый формат

```json
{
  "schema_version": 2,
  "updated_at": "2026-08-22T10:00:00+05:00",
  "users": {
    "896915843": {
      "user_id": "896915843",
      "name": "Пример Сотрудник",
      "normalized_name": "пример сотрудник",
      "aliases": [
        "896915843",
        "excel_primer_sotrudnik"
      ],
      "registration_status": "registered",
      "telegram": {
        "username": "example_user",
        "first_name": "Пример",
        "last_name": "Сотрудник",
        "last_seen_at": "2026-08-22T09:58:00+05:00"
      },
      "created_at": "2026-07-01T08:00:00+05:00",
      "updated_at": "2026-08-22T09:58:00+05:00"
    },
    "excel_drugoi_sotrudnik": {
      "user_id": "excel_drugoi_sotrudnik",
      "name": "Другой Сотрудник",
      "normalized_name": "другой сотрудник",
      "aliases": [
        "excel_drugoi_sotrudnik"
      ],
      "registration_status": "excel_only",
      "telegram": null,
      "created_at": "2026-08-22T10:00:00+05:00",
      "updated_at": "2026-08-22T10:00:00+05:00"
    }
  }
}
```

### 3.3. Поля

| Поле | Тип | Обязательность | Назначение |
|---|---|---:|---|
| `schema_version` | integer | да | Версия структуры файла |
| `updated_at` | ISO datetime | да | Время последнего изменения |
| `users` | object | да | Реестр, индексированный каноническим `user_id` |
| `user_id` | string | да | Канонический ID записи |
| `name` | string | да | Отображаемое ФИО |
| `normalized_name` | string | да | Нормализованный ключ для сопоставления |
| `aliases` | array[string] | да | Старые Excel-ID и прежние идентификаторы |
| `registration_status` | enum | да | `registered`, `excel_only`, `blocked`, `archived` |
| `telegram` | object/null | да | Telegram-профиль или `null` для Excel-only |
| `created_at` | ISO datetime | да | Дата создания записи |
| `updated_at` | ISO datetime | да | Дата изменения записи |

### 3.4. Нормализация

`normalized_name` формируется одинаково во всех слоях: обрезаются внешние пробелы, последовательности пробелов заменяются одним пробелом, строка переводится в нижний регистр. Для критичных операций нужно дополнительно проверять дубликаты нормализованных ФИО.

Если два Telegram ID имеют одинаковое ФИО, автоматическое объединение выполнять нельзя. Бот должен показать конфликт администратору и потребовать ручного выбора основной записи.

## 4. groups.json — организационная иерархия

### 4.1. Назначение

`groups.json` связывает пользователя с группой, руководителем и организационной веткой. Именно этот файл определяет, какие сотрудники входят в расчёт `coor A`, `coor R`, `SPV` и `MNG`.

### 4.2. Рекомендуемый формат

```json
{
  "schema_version": 2,
  "hierarchy_version": "org_2026_08",
  "updated_at": "2026-08-22T10:00:00+05:00",
  "group_definitions": {
    "MNG": {
      "level": 1,
      "parent_group": null,
      "children_groups": ["SPV"],
      "kpi_scope": ["A LAMP", "R LAMP"]
    },
    "SPV": {
      "level": 2,
      "parent_group": "MNG",
      "children_groups": ["coor A", "coor R"],
      "kpi_scope": ["A LAMP", "R LAMP"]
    },
    "coor A": {
      "level": 3,
      "parent_group": "SPV",
      "children_groups": ["A LAMP"],
      "kpi_scope": ["A LAMP"]
    },
    "coor R": {
      "level": 3,
      "parent_group": "SPV",
      "children_groups": ["R LAMP"],
      "kpi_scope": ["R LAMP"]
    },
    "A LAMP": {
      "level": 4,
      "parent_group": "coor A",
      "children_groups": [],
      "kpi_scope": ["A LAMP"]
    },
    "R LAMP": {
      "level": 4,
      "parent_group": "coor R",
      "children_groups": [],
      "kpi_scope": ["R LAMP"]
    }
  },
  "assignments": {
    "896915843": {
      "user_id": "896915843",
      "group": "A LAMP",
      "manager_id": "123456789",
      "branch": "A",
      "active": true,
      "assigned_at": "2026-07-01T08:00:00+05:00",
      "updated_at": "2026-08-22T10:00:00+05:00"
    },
    "123456789": {
      "user_id": "123456789",
      "group": "coor A",
      "manager_id": "234567890",
      "branch": "A",
      "active": true,
      "assigned_at": "2026-07-01T08:00:00+05:00",
      "updated_at": "2026-08-22T10:00:00+05:00"
    }
  }
}
```

### 4.3. Поля назначений

| Поле | Тип | Назначение |
|---|---|---|
| `user_id` | string | Ссылка на `users.json` |
| `group` | enum | `MNG`, `SPV`, `coor A`, `coor R`, `A LAMP`, `R LAMP` |
| `manager_id` | string/null | Непосредственный руководитель |
| `branch` | enum/null | `A`, `R` или `null` для общего уровня |
| `active` | boolean | Учитывать ли запись в текущей иерархии |
| `assigned_at` | ISO datetime | Дата назначения |
| `updated_at` | ISO datetime | Дата изменения назначения |

`group_definitions` является справочником структуры, а `assignments` — фактическими назначениями людей. Это позволяет изменить руководителя или группу без изменения описания иерархии.

### 4.4. Области расчёта

| Группа руководителя | `kpi_scope` |
|---|---|
| `coor A` | Только `A LAMP` |
| `coor R` | Только `R LAMP` |
| `SPV` | `A LAMP` и `R LAMP` |
| `MNG` | `A LAMP` и `R LAMP` |

Для отчётности `SPV` и `MNG` должны дополнительно получать разбивку по веткам A/R, даже если общий KPI считается по обеим командам.

## 5. team_kpi_data.json — производный командный KPI

### 5.1. Назначение

`team_kpi_data.json` хранит результаты расчёта на основании исходного KPI сотрудников, состава групп и версии формул. Файл можно полностью пересобрать из исходных данных. Он не является источником истины для личного KPI сотрудника.

### 5.2. Рекомендуемый формат

```json
{
  "schema_version": 1,
  "calculation_version": "weighted_v1",
  "updated_at": "2026-08-22T10:05:00+05:00",
  "current_period": "2026-08",
  "periods": {
    "2026-08": {
      "period": "2026-08",
      "kpi_schema_version": "employee_kpi_v1",
      "organization_version": "org_2026_08",
      "source_import_id": "kpi_import_2026-08-22T10:00:00Z",
      "calculated_at": "2026-08-22T10:05:00+05:00",
      "calculation_status": "complete",
      "teams": {
        "A LAMP": {
          "team_group": "A LAMP",
          "manager_groups": ["coor A"],
          "branch": "A",
          "employee_ids": ["896915843"],
          "employee_count": 1,
          "metrics": {
            "gt": {
              "plan": 100,
              "fact": 80,
              "percent": 80.0
            },
            "microacts": {
              "plan": 128,
              "fact": 100,
              "las_fact": 55,
              "lau_fact": 45,
              "percent": 78.125,
              "las_percent": 55.0,
              "las_threshold_percent": 40.0,
              "las_threshold_status": "pass"
            },
            "retrafic": {
              "plan": 15,
              "fact": 12,
              "percent": 80.0
            }
          },
          "overall": {
            "percent": null,
            "status": "not_configured",
            "weights": null
          },
          "quality": {
            "missing_employee_ids": [],
            "zero_plan_metrics": [],
            "duplicate_names": [],
            "warnings": []
          }
        },
        "R LAMP": {
          "team_group": "R LAMP",
          "manager_groups": ["coor R"],
          "branch": "R",
          "employee_ids": [],
          "employee_count": 0,
          "metrics": {
            "gt": {"plan": 0, "fact": 0, "percent": 0},
            "microacts": {"plan": 0, "fact": 0, "las_fact": 0, "lau_fact": 0, "percent": 0, "las_percent": 0, "las_threshold_percent": 40, "las_threshold_status": "no_data"},
            "retrafic": {"plan": 0, "fact": 0, "percent": 0}
          },
          "overall": {"percent": null, "status": "not_configured", "weights": null},
          "quality": {"missing_employee_ids": [], "zero_plan_metrics": [], "duplicate_names": [], "warnings": []}
        }
      },
      "manager_reports": {
        "coor A": {
          "manager_group": "coor A",
          "scope_groups": ["A LAMP"],
          "team_keys": ["A LAMP"],
          "employee_ids": ["896915843"],
          "employee_count": 1,
          "metrics": {
            "gt": {"plan": 100, "fact": 80, "percent": 80.0},
            "microacts": {"plan": 128, "fact": 100, "las_fact": 55, "lau_fact": 45, "percent": 78.125, "las_percent": 55.0, "las_threshold_percent": 40.0, "las_threshold_status": "pass"},
            "retrafic": {"plan": 15, "fact": 12, "percent": 80.0}
          },
          "overall": {"percent": null, "status": "not_configured", "weights": null},
          "quality": {"missing_employee_ids": [], "zero_plan_metrics": [], "duplicate_names": [], "warnings": []}
        },
        "coor R": {
          "manager_group": "coor R",
          "scope_groups": ["R LAMP"],
          "team_keys": ["R LAMP"],
          "employee_ids": [],
          "employee_count": 0,
          "metrics": {},
          "overall": {"percent": null, "status": "no_data", "weights": null},
          "quality": {"missing_employee_ids": [], "zero_plan_metrics": [], "duplicate_names": [], "warnings": []}
        },
        "SPV": {
          "manager_group": "SPV",
          "scope_groups": ["A LAMP", "R LAMP"],
          "team_keys": ["A LAMP", "R LAMP"],
          "employee_ids": ["896915843"],
          "employee_count": 1,
          "metrics": {},
          "overall": {"percent": null, "status": "not_configured", "weights": null},
          "quality": {"missing_employee_ids": [], "zero_plan_metrics": [], "duplicate_names": [], "warnings": []}
        },
        "MNG": {
          "manager_group": "MNG",
          "scope_groups": ["A LAMP", "R LAMP"],
          "team_keys": ["A LAMP", "R LAMP"],
          "employee_ids": ["896915843"],
          "employee_count": 1,
          "metrics": {},
          "overall": {"percent": null, "status": "not_configured", "weights": null},
          "quality": {"missing_employee_ids": [], "zero_plan_metrics": [], "duplicate_names": [], "warnings": []}
        }
      }
    }
  }
}
```

В production-примере `metrics` для `SPV` и `MNG` должны быть заполнены. В сокращённом примере они оставлены пустыми, потому что общий итог и веточные итоги лучше разделять отдельными объектами.

### 5.3. Рекомендуемая детализация manager_reports

Для `SPV` и `MNG` полезно хранить не только общий итог, но и ветки:

```json
{
  "manager_reports": {
    "SPV": {
      "overall": {
        "metrics": {
          "gt": {"plan": 900, "fact": 735, "percent": 81.6667},
          "microacts": {"plan": 1200, "fact": 1040, "percent": 86.6667},
          "retrafic": {"plan": 140, "fact": 124, "percent": 88.5714}
        }
      },
      "by_branch": {
        "A": {"team_keys": ["A LAMP"], "metrics": {}},
        "R": {"team_keys": ["R LAMP"], "metrics": {}}
      }
    }
  }
}
```

## 6. Формулы

Для каждой команды расчёт выполняется по сотрудникам, входящим в `employee_ids`.

```text
GT % = сумма(gt_fact) / сумма(gt_plan) × 100

Микроакты факт = сумма(micro_las_fact + micro_lau_fact)

Микроакты % = сумма(microacts_fact) / сумма(micro_plan) × 100

LAS % = сумма(micro_las_fact) /
        сумма(micro_las_fact + micro_lau_fact) × 100

Re-trafic % = сумма(retrafic_fact) /
              сумма(retrafic_plan) × 100
```

Если план равен нулю, процент должен быть `0`, а в `quality.zero_plan_metrics` добавляется соответствующий показатель. Если общая формула взвешенного KPI ещё не утверждена, `overall.percent` должен быть `null`, а `overall.status` — `not_configured`. Нельзя придумывать общий процент простым средним без согласованных весов.

Когда веса утверждены, их нужно хранить рядом с результатом:

```json
{
  "overall": {
    "percent": 84.9,
    "status": "calculated",
    "weights": {
      "gt": 0.4,
      "microacts": 0.4,
      "retrafic": 0.2
    }
  }
}
```

## 7. Процесс импорта и пересчёта

1. Бот принимает Excel только с KPI сотрудников `A LAMP` и `R LAMP`.
2. Импорт проверяет обязательные колонки, дубликаты, отрицательные значения и соответствие сотрудников единому реестру.
3. Строки `coor A`, `coor R`, `SPV` и `MNG` блокируются как недопустимые для исходного KPI-файла.
4. После preview выполняется backup runtime-данных в приватный репозиторий.
5. В транзакции обновляется личный KPI сотрудников и, при необходимости, добавляются только безопасные Excel-only записи.
6. После успешной записи `TeamKpiService` строит `team_kpi_data.json` из `users`, `groups` и личного KPI.
7. Командный файл записывается атомарно после успешного расчёта.
8. Уведомления отправляются сотрудникам об обновлении личных KPI, а руководителям — о готовности командного отчёта.

## 8. Проверки целостности

Перед публикацией нового командного расчёта должны выполняться следующие проверки:

| Проверка | Ожидаемое поведение |
|---|---|
| Зарегистрированный сотрудник исчез из Excel | Не удалять его, показать предупреждение или заблокировать импорт по политике |
| В Excel есть руководитель | Заблокировать импорт |
| Сотрудник есть в Excel, но нет в users/groups | Не создавать молча назначение в команду; показать ошибку сопоставления |
| Два сотрудника имеют одинаковое нормализованное ФИО | Требовать ручного разрешения конфликта |
| У сотрудника нет KPI-записи | Включить в `missing_employee_ids`, не считать как нулевого без явного правила |
| План равен нулю | Процент `0`, запись в `zero_plan_metrics` |
| Поменялся состав группы | Новый расчёт получает новую `organization_version` |
| Повторный пересчёт тех же исходных данных | Результат должен быть идентичным и не дублировать записи |
| Ошибка записи team KPI | Не изменять уже опубликованный рабочий расчёт |

## 9. Периоды и история

`team_kpi_data.json` должен быть месячным. Поля `current_period` и `periods[YYYY-MM]` позволяют закрывать предыдущий месяц без удаления истории. Для каждого периода нужно сохранять:

- `kpi_schema_version` — версию состава показателей;
- `organization_version` — версию иерархии;
- `source_import_id` — импорт, на котором построен расчёт;
- `calculated_at` — время пересчёта;
- `calculation_status` — `complete`, `warning`, `failed` или `no_data`.

При полной смене KPI создаётся новый `kpi_schema_version`, например `employee_kpi_v2`. Старые периоды остаются на старой схеме и не пересчитываются автоматически по новым правилам.

## 10. Миграция с текущего формата

Переход следует выполнить поэтапно:

1. Оставить текущие `users.json` и `groups.json` читаемыми через backward-compatible reader.
2. Перевести верхний уровень users в объект с метаданными и вложенным `users`, не удаляя старые поля до завершения миграции.
3. Добавить `normalized_name`, `aliases`, `registration_status` и timestamps.
4. Нормализовать назначения групп и добавить `manager_id`, `branch` и `active`.
5. Создать `team_kpi_data.json` как новый файл, не изменяя исходный `kpi_data.json` до завершения тестов.
6. Запустить параллельный расчёт и сравнить командный отчёт с текущим отчётом «Моя команда».
7. После проверки переключить экран руководителя на `team_kpi_data.json` или на пересчёт через `TeamKpiService`.
8. Только после успешного полного CI включить блокировку руководительских строк в Excel.

## 11. Итоговое разделение ответственности

| Файл | Источник истины | Что хранит | Чего не должен хранить |
|---|---|---|---|
| `users.json` | Да | Личность, Telegram ID, aliases, статус регистрации | KPI, планы, командные проценты |
| `groups.json` | Да | Группа, руководитель, ветка, активность, справочник иерархии | Фактические KPI |
| `team_kpi_data.json` | Нет, производный слой | Месячные командные и руководительские расчёты, качество данных, версии источников | Независимо введённые личные KPI |

Такое разделение позволяет загружать только KPI `A LAMP/R LAMP`, автоматически строить показатели `coor A/R`, `SPV` и `MNG`, сохранять историю по месяцам и безопасно пересчитывать командные отчёты после исправления исходных данных.
