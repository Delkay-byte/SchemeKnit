# Zero-Cost Backup and Restore Runbook (Pilot)

Date: 2026-10-31  
Applies to: Neon Free pilot database and the Render free pilot services.

**This runbook has not been executed against a live database.** It is a safe procedure for the
owner to follow manually. Do not run a restore against production, and do not paste connection
strings into chat, logs, source files or screenshots.

## What exists today

| Item | Status | Evidence |
|---|---|---|
| Neon automated scheduled backup | Not available on Free | Neon Free includes a 6-hour restore window and 1 manual snapshot, not scheduled backups |
| Neon manual snapshot | Available | Console > project > Branches > Snapshots |
| Manual logical dump (`pg_dump`) | Available | Requires a direct (non-pooler) Neon URL |
| Restore tested | No | No pilot database exists yet |
| Object storage backup | Not applicable yet | R2 bucket `schemeknit` exists but is empty; uploads currently use ephemeral disk |
| Uploaded originals durable | No | Local disk on Render is lost on restart/sleep/redeploy |

## Before the pilot

1. In Neon, create a manual snapshot of the pilot project and label it `pre-pilot`.
2. Take a logical dump with a direct URL:

```bash
export PILOT_DIRECT_URL='postgresql://...@ep-...neon.tech/neondb?sslmode=require'
pg_dump "$PILOT_DIRECT_URL" \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file="schemeknit-pilot-$(date +%Y%m%d-%H%M).dump"
```

3. Store the dump outside the repository (encrypted disk or private storage). Do not commit it.
4. Record the dump date, size and Neon snapshot name in the pilot log.

## During the pilot

- Take a manual Neon snapshot before any schema migration, and at least weekly.
- Take a logical dump weekly and before inviting a new batch of teachers.
- Check `GET /api/ready` and the Render logs after every deploy.
- Remember that original upload files are not durable. Parsed curriculum, users, lessons and
  exports-in-database survive; a multi-subject upload may need to be repeated after a restart.

## Restore into a verified pilot database only

> **Destructive operation.** Confirm the target is the empty pilot database, not production.
> Prefer restoring into a new empty Neon project or branch, then switching the pilot service to
> it. Never use `--clean` against production.

```bash
export PILOT_RESTORE_URL='postgresql://...@ep-...neon.tech/neondb?sslmode=require'
pg_restore \
  --clean --if-exists \
  --no-owner --no-privileges \
  --dbname="$PILOT_RESTORE_URL" \
  schemeknit-pilot-YYYYMMDD-HHMM.dump
```

If the target is a brand-new empty database, omit `--clean --if-exists`.

## Verify the restore

1. Start the pilot backend and check `GET /api/health` and `GET /api/ready` both return 200.
2. Sign in with a known pilot account.
3. Confirm the dashboard lists the expected schemes and lessons.
4. Open one lesson, edit and save it, then reload.
5. Export one DOCX and one PDF.
6. Check the Neon console for connection and storage errors.
7. Record the verification result and any missing data in the pilot log.

## If email is needed

`onboarding@resend.dev` cannot send password-reset email to external teachers. Until a domain is
verified in Resend, reset a pilot teacher's password from the platform-admin surface. Do not
promise testers self-service password reset.

## Retention

- Keep the pre-pilot dump until the pilot is closed.
- Keep at least the two most recent weekly dumps.
- Delete pilot data only after the owner has exported anything needed and confirmed the pilot is
  closed.
