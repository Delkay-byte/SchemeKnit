# Friends-and-Family Pilot Plan

Date: 2026-10-31  
Status: **NOT STARTED — zero-cost path assessed; owner provisioning required**

See `docs/infrastructure/ZERO-COST-INFRASTRUCTURE-ASSESSMENT.md` for the free-tier
architecture, limits and owner-side setup.

## Goal

A small, trusted group validates real lesson-planning workflows for a controlled
period. No public invitation, no live payments.

## Participants

- 3–8 trusted teachers across KG, primary and JHS.
- At least one school administrator if school workflows are included.
- Synthetic/approved test curriculum documents only.

## Test accounts

- Create one account per participant with a unique email.
- Use Free tier or explicitly granted pilot credits.
- Do not share accounts.
- Keep payment disabled.
- **This pilot release keeps invite-only registration.** Set backend
  `REGISTRATION_MODE=invite_only` with `PILOT_INVITE_CODE` and frontend
  `NEXT_PUBLIC_PILOT_INVITE_REQUIRED=true`. Never commit the code.
- `/signup` still reads `GET /api/auth/registration-policy` at runtime and the
  backend remains the enforcement point: the build-time flag cannot bypass the
  invite check. Turnstile and the password policy stay enforced in every mode.
- Public (`open`) or disabled (`closed`) registration remain supported for a
  later release; changing mode is an environment-only decision.

## Scenarios

1. Register and sign in.
2. Upload a real Scheme of Learning (DOCX/PDF).
3. Review extracted week/strand/sub-strand/content standard/indicators.
4. Generate one KG, one primary and one JHS lesson.
5. Edit and save a lesson; reload.
6. Export DOCX and PDF.
7. Trigger a controlled provider failure and observe a safe error (admin-only).
8. Exercise the free credit allowance and cache replay.
9. Reset password and sign out.
10. Report any incorrect curriculum mapping or unsafe content.

## Bug report template

- Participant ID (not email):
- Browser/device:
- Class/subject/indicator:
- Steps:
- Expected:
- Actual:
- Screenshot (no personal data):
- Severity:

## Feedback template

- Was the lesson usable without major rewriting?
- Were objectives/activities/assessment aligned?
- Were resources realistic?
- Was export usable?
- What took the most time?
- What would stop you using it weekly?

## Data and safety

- No API keys, logs or other users' data to testers.
- No live payments.
- Do not upload sensitive personal documents. The upload page now carries the
  exact owner-approved privacy notice; testers must remove pupil names, grades
  and other identifiable records before upload.
- Original upload files are on ephemeral free-host disk. Complete multi-subject
  confirmation before the service sleeps; parsed curriculum persists in PostgreSQL.
- External password-reset email is unavailable while `EMAIL_FROM` uses
  `resend.dev`; reset pilot passwords from the platform-admin surface.
- Take a manual Neon snapshot/dump before the pilot and weekly.
- Remove pilot accounts/data after the pilot if required.
