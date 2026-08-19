# Registration failure findings

## Root causes

The registration handler writes a dictionary record to `pending_requests.json` with `name`, `group`, and `created_at`. The legacy admin pending flow assumed pending values were strings, while the direct `adm_accept/adm_reject` callback and the unified `req_accept/req_reject` inbox both processed the same pending record. This created two moderation paths and allowed stale callbacks to process the same request twice.

`storage.py` used atomic replacement but had no per-file async lock or serialized read-modify-write helper. Multiple registration or moderation updates could therefore load the same JSON snapshot and overwrite another update.

## Resolution

The pending store now uses a per-file `asyncio.Lock` and the `update_pending()` read-modify-write helper. New registration notifications use only the unified `req_accept`/`req_reject` inbox callbacks, while the obsolete global `adm_` callback route is no longer registered. `/start` also detects an already-pending request and avoids creating a duplicate request for the same user.

The behavior audit now simulates 25 concurrent pending-request additions, concurrent removals, and duplicate removal attempts. All audit suites pass, commit `2b22dcd` is deployed on Render, and `GET /healthz` returns HTTP 200.
