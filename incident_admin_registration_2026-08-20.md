# Incident: bot stopped after admin registration

## Observed Render evidence

Render Application Logs around 02:55 AM showed a Telegram polling conflict:

`telegram.error.Conflict: Conflict: terminated by other getUpdates request; make sure that only one bot instance is running`

Immediately afterward the application logged `Application is stopping`, `Scheduler has been shut down`, and `Application.stop() complete`. The service then became live again and scheduled jobs executed successfully. The available traceback did not show a JSON or registration exception.

## Root cause and remediation

The direct outage evidence was a polling ownership conflict, likely occurring while another bot process or deployment still held `getUpdates`. The recovery loop was retained but its retry delay was increased from 5 to 15 seconds so an old Render process has time to release polling ownership.

Separately, the registration flow allowed `ADMIN_ID` to enter the ordinary user path. This could create self-moderation and inconsistent admin/user state. The bot now recognizes `ADMIN_ID` before all normal registration checks, immediately returns the admin menu, blocks every registration step for that ID, and removes stale admin records from users, groups, pending requests, drafts, team requests, and teams during startup.

The regression audit includes the admin-record cleanup test and all existing registration/concurrency tests. All local audits pass.
