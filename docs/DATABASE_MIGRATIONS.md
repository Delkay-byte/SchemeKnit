# TeachFlow Database Migrations

## Overview

TeachFlow uses a versioned migration system to apply schema changes safely.

## Migration Files

Located in `backend/src/migrations/`:

| Version | Name | Description |
|---------|------|-------------|
| v001 | Educational taxonomy | Adds educational_level, template_id, and new fields to lesson_plans |
| v002 | Payment tables | Creates payments, audit logs, product plans, payment config tables |
| v003 | Admin flag | Adds is_admin column to users table |

## How Migrations Run

1. On application startup, `migration_runner.run_all_migrations()` is called
2. The runner checks `teachflow_migrations` table for already-applied versions
3. Each pending migration is applied in order
4. Applied migrations are recorded with version, name, and timestamp

## Safety

- **Non-destructive**: New columns are added with defaults, existing data is preserved
- **Idempotent**: Running migrations multiple times is safe
- **Tracked**: All applied migrations are recorded in `teachflow_migrations` table

## Rollback

Each migration has a `down()` function, but rollback is limited:

- Adding columns: Cannot safely remove columns without data loss
- Creating tables: Can drop tables, but this loses data

**Recommendation**: Always backup before rollback.

## Production Deployment

1. Backup existing database
2. Deploy new code
3. Application runs migrations automatically on startup
4. Verify migration status: `GET /api/health`

## Manual Migration

```python
from src.migration_runner import run_all_migrations
results = run_all_migrations()
```

## Backup Requirement

**Before any migration:**
```bash
cp teachflow.db teachflow.db.backup.$(date +%Y%m%d)
```
