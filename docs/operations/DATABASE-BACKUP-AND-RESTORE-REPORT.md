# Database Backup and Restore Report

Date: 2026-10-31  
Status: **BLOCKED — no production/staging database access**

## Findings

- Production database is PostgreSQL/Neon according to deployment documentation,
  but no Neon/Render credentials or dashboard access are available in this
  environment.
- Runtime, migration and backup roles cannot be inspected.
- Automated backup frequency, retention, encryption, storage location and
  recovery objectives cannot be confirmed.
- No production or staging restore was attempted.

## Required owner actions

1. Confirm Neon/Render database plan and backup retention.
2. Identify runtime role, migration role and backup/admin role.
3. Confirm least privilege: runtime role must not be superuser/owner.
4. Configure encrypted backups with documented retention/RPO/RTO.
5. Restore a backup into a disposable staging database.
6. Verify migrations, users, catalogue, lessons, credits and payment records.
7. Record restore duration and integrity results.

## Local evidence

The application migrations and SQLite/PostgreSQL portability are covered by the
existing migration tests, but that is not a backup/restore test.

No restore success is claimed.
