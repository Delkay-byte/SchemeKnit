# Weekly-Plan Persistence Topology

Date: 2026-11-02
Repository: `Delkay-byte/SchemeKnit`

## 1. Hosted backend

Verified read-only through the Render API:

| Item | Evidence |
|---|---|
| Service | `schemeknit-api` (`srv-damsbb1ntn7c73d7eg10`) |
| Type | `web_service` |
| Instances | `serviceDetails.numInstances = 1` |
| Plan | `free` |
| Auto-deploy | `no` (release workflow deploys by commit) |
| Start command | `cd backend && python -m uvicorn src.main:app --host 0.0.0.0 --port $PORT` |
| Workers | none configured; Uvicorn default single worker |
| `WEB_CONCURRENCY` | not present in the 60 environment keys |
| Background workers/cron | no other SchemeKnit service is registered |

One Render service does **not** prove one process forever. A platform restart,
manual redeploy or a future worker-count change can create a new process with a
fresh ephemeral filesystem. The current start command is single-process.

## 2. Filesystem consequences

Render's filesystem is not the authoritative database and is not shared between
instances. The legacy code wrote `backend/teachflow_data/weekly_plans.json`
relative to the process working directory. Consequences:

- a restart/redeploy can lose or replace the file;
- two processes could read-modify-write the same file and lose an update;
- a process-local `threading.Lock` cannot protect across processes;
- the current production container's file cannot be inspected read-only through
  the Render API.

The repository-local file is not production evidence. It contains seven test
fixture records:

- six records owned by `accept-teacher-0001` from September acceptance runs;
- one `wp-ux-fixture` record from the November UX acceptance run.

None is a real teacher or school record.

## 3. Production database state

Read-only PostgreSQL inspection of the production `DATABASE_URL` (value never
printed or stored):

- `weekly_class_plans` did not exist before this branch.
- no alternative weekly-plan table exists (`pg_tables` shows only `weeks`).
- zero weekly-plan rows exist in any known database representation.

This matches the owner's zero-record statement.

## 4. Target architecture

`weekly_class_plans` is the authoritative hosted store:

- `id` stable plan identity;
- `owner_id` FK to `users`, indexed;
- `school_id` nullable FK for school scope;
- query columns for class, week, term, academic year and template;
- `content` JSONB on PostgreSQL (JSON on SQLite);
- `revision` monotonic integer used as the `If-Match` token;
- `created_at` / `updated_at`.

Updates use a conditional `UPDATE ... WHERE id = ? AND owner_id = ? AND
revision = ?`, incrementing `revision` once. PostgreSQL enforces the winner;
SQLite's write serialization plus the same predicate gives equivalent local
behaviour. No Python process lock is the authority.

## 5. Concurrency implications

- Two requests with the same revision: one `rowcount = 1`, one `rowcount = 0`;
  the loser receives 409.
- A stale client cannot overwrite a newer row.
- A transaction/connection failure returns a controlled 503 and does not
  fall back to the JSON file.
- Reads always query the database; the JSON file is not a read fallback.

## 6. Residual risks

- The current Render plan is single-instance; the database design no longer
  depends on that.
- The legacy production file (if any) is inaccessible. The importer exists for
  a dry-run if it is later retrieved; it never deletes the source.
- No real production weekly-plan data has been observed.
