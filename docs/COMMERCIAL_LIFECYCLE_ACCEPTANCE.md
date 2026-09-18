# Commercial Lifecycle Acceptance (Discovery)

Date: 2026-09-16. Web app is source of truth. No code changed. Disposable data prefixed DISC-.

## Lifecycle (verified live)

```
PLATFORM ADMIN
  | Create School → Create License (pending) → Activate → Generate Code (TF-SCH-…)
  v
SCHOOL ACTIVATION (/activate-school, logged out)
  | Validate code (display-only: school/plan/status/seats/expiry)
  | Create School Admin (name/email/password≥8+confirm) → code redeemed atomically
  v
SCHOOL ADMIN (/school-admin)
  | Dashboard (plan/status/expiry/seats) → Add Teachers (role/school server-forced)
  v
TEACHER (/dashboard)
  | Upload → Review → Approve → Configure → Generate → Edit → Export
```

## When things exist / begin / restrict
- School row: at PA creation (status active, no license yet).
- License row: at PA creation (status pending → active on activate or first code redeem).
- Activation code: per license, `active` until used/revoked/expired.
- School Admin account: ONLY at code redemption (no pre-creation path; setup without
  code → 422; suspended-license code → 403; used code → 403; unknown code → 404).
- Teacher account: ONLY via school admin (`POST /users`) or platform admin register
  (used for unassigned/free-tier accounts). Anonymous self-register → 401.
- Teacher access begins: immediately (free tier if no school; licensed tier if school licensed).
- Restriction: suspended/expired/missing license → teacher workflow 403 + teacher
  creation 403; data, lessons, templates preserved; reactivation restores.
- Who creates whom: PA → school/license/code; code → school admin; school admin →
  teachers. Teachers create nothing but lesson content.

## Direct answers to the three desktop questions
1. **Scheme deletion**: WEB supports Option A today — own scheme without generated
   content deletes (200 + storage file cleaned); with content → 409 with message;
   another teacher's → 403; missing → 404. UI offers an icon delete per scheme. Desktop's
   inability is a client/build gap, not a missing backend capability.
2. **Ollama without license**: WEB behaves identically — the AI endpoint checks
   ownership only, never license. See decision matrix; flagged below.
3. **Lifecycle roles**: PA = commercial control plane; School Admin = one-school
   workspace manager (exists only post-activation); Teacher = lesson producer
   (free-tier when unassigned, entitled tier when licensed).

## Dependencies of a scheme (for delete design)
weeks (cascade) · term_configs · generation jobs · lesson plans · export events ·
storage file · AI enrichment cache (via lessons). Jobs/lessons/events block deletion
(FK on PostgreSQL; silent orphans pre-guard on SQLite) — hence current 409 behavior.
