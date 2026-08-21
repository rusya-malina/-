# Deep audit findings

## Baseline

- Audit backup: `backups/20260821T112214Z_deep_audit/`.
- Local HEAD at audit start: `01c6d5b`.
- Render service: `not_suspended`; latest Render deploy: `live`, commit `f863ab6`.
- Architecture, deep audit, behavior audit, runtime name audit, Ruff and compileall passed at baseline.

## Confirmed findings

F-004 and F-005 are resolved and production-verified in commit `9b8d710`. Render reports the deploy as `live`, and the service responds with HTTP 200 on `/` and `/healthz`.

### F-001: GitHub remote drift from production KPI sync

`origin/main` is ahead of local HEAD by commit `f863ab6`, titled `Persist newly uploaded KPI snapshot`. The commit contains only `kpi_data.json` and `uploaded_data/latest_kpi.xlsx`; no Python source changed. This is the expected result of the runtime GitHub KPI sync, but it creates a moving production branch and local/remote data drift that must be explicitly handled in the audit.

### F-002: Legacy Telegram adapters still bypass application services

The current handlers still contain direct storage boundaries in legacy flows, including manual KPI employee deletion in `handlers/kpi.py` and direct reads in several presentation handlers. Profile-name mutation has been moved out of `handlers/user.py` into `ProfileService`. The remaining boundaries are not necessarily functional defects, but they are architectural coupling points for a subsequent vertical slice and must be checked against atomicity, permissions, and regression coverage.

### F-003: KPI notification matching required canonical user extraction

The notification matcher was recently corrected to extract `name` from canonical user records. The dedicated notification regression test passes; this path remains part of the cross-flow audit.

## Audit execution result

The role, route, data-integrity, concurrency, import, registration, reporting, notification, polling, startup, behavior, and runtime-name checks were executed. Ruff, compileall, pip check, and the complete regression suite passed locally.

Focused regression coverage now includes `tools/test_profile_service.py` for cross-file profile rename and `tools/test_admin_delete_flow.py` for delete permission and notification ordering.

### F-004: Profile rename split-brain risk — fixed

`handlers/user.py::save_new_full_name` now delegates to `ProfileService.rename()`. The service updates `users.json`, `groups.json`, the normalized KPI key/name, and linked issuance names in one ordered `JsonTransaction`, with conflict and not-found results. The profile contract test covers propagation, conflict handling, missing users, and idempotent rename behavior.

### F-005: Delete notification precedes delete commit — fixed

`handlers/admin.py::process_delete_user_by_number` now performs a permission check at the state boundary, invokes `EmployeeAdminService.delete_registered()`, and sends the stop notification only after a successful operation result. The delete-flow regression test verifies that failed deletion does not notify and successful deletion does notify.

## Publication and production verification

The changes were rebased onto the KPI snapshot commit `f863ab6` and published to `origin/main` as commit `9b8d710`. Render deploy `dep-da43f51srm7s73dd0kn0` for that commit reached `live`. The service is `not_suspended`; `https://test-project-0seb.onrender.com/` and `/healthz` both returned HTTP 200 with body `OK`. The `/health` path is not implemented and correctly returns HTTP 404.
