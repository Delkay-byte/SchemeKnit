# Public Entry + Role Architecture

How a visitor reaches TeachFlow, which login they use, and how the backend
decides what they can do. Web only — Desktop is out of scope for this layer.

## Architecture

```
                         TEACHFLOW
                            │
                    PUBLIC LANDING PAGE
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
   PLATFORM ADMIN     SCHOOL ADMIN          TEACHER
   /login/platform-   /login/school-       /login
   admin              admin                   │
                                             │
                              ┌───────────────┴───────────────┐
                              │                               │
                         SCHOOL TEACHER                 INDIVIDUAL TEACHER
                              │                               │
                       School entitlement              Free Teacher
                                                        or Teacher Pro
```

School Admin branch:

```
PUBLIC
→ School Administration
→ /activate-school
→ Activation Code
→ School Admin Account Creation
→ /school-admin/
```

## Three login experiences, four user situations

There are **three** primary login pages and **four** kinds of user. School
Teachers and Individual Teachers share one login (`/login`) — the backend
resolves which entitlement applies. There is no fourth teacher login system.

| User | Login route | Lands on |
|---|---|---|
| Platform Admin | `/login/platform-admin` | `/platform-admin/` |
| School Admin / Headteacher | `/login/school-admin` | `/school-admin/` |
| School Teacher | `/login` | `/dashboard` |
| Individual Teacher | `/login` | `/dashboard` |

Role routing after login is decided by the **backend role**, never by the URL
the visitor typed or anything the browser asserts.

## Public landing page (`/`)

Three visually distinct, cohesive cards so a visitor immediately knows which
door is theirs. It is a marketing/entry page, not an internal dashboard.

- **Platform Administration** (slate) — "Platform Admin Login" → `/login/platform-admin`
- **School Administration** (emerald) — "Activate Your School" → `/activate-school`, plus "School Admin Login" → `/login/school-admin`
- **Teacher** (blue) — "Teacher Login" → `/login`, plus "Create Free Teacher Account" → `/signup`

A live session skips the landing page and goes straight to the role console.

## Platform Admin entry (`/login/platform-admin`)

Labelled "TeachFlow Platform Administration". Purpose: schools, plans,
licenses, activation codes, payments, platform audit, platform operations.
No teacher or school-admin workflow is shown here. After login →
`/platform-admin/`. Backend authorization is authoritative; a teacher typing
the route cannot gain access.

## School Admin entry (`/login/school-admin`)

Labelled "TeachFlow School Administration". Purpose: school, teachers, seats,
school settings, school license information.

A School Admin account **cannot** be created from this page. The login card
links "Have a school activation code?" → `/activate-school` for schools that
have not yet been activated.

## School activation must precede School Admin creation (§6)

The commercial lifecycle is unchanged:

```
Platform Admin
→ creates school
→ creates/activates school license
→ generates activation code
→ gives activation code to Headteacher

Headteacher
→ opens /activate-school
→ enters activation code
→ validates code
→ sees school/plan/seats/expiry
→ creates School Admin account
→ activation code is atomically redeemed
→ account becomes active
→ redirect to /school-admin/
```

The activation code is an **onboarding credential, not a login credential**.
After redemption the headteacher signs in normally with email + password at
`/login/school-admin` and never needs the code again.

### Activation page (`/activate-school`)

Four steps:

1. **Code** — enter the activation code
2. **Validate** — shows safe info only: school name, plan, teacher seats,
   expiry date, license status. No activation secrets, internal IDs, payment
   secrets or database data are revealed.
3. **Account** — full name, email, password, confirm password (existing email
   validation, password policy, password eye toggle, live match indicator)
4. **Activate School** — server atomically validates the code, validates the
   license, associates the school, creates the School Admin, redeems the code,
   activates the license, and audits the event. On success → `/login/school-admin`.

### Activation states

| State | Result |
|---|---|
| Invalid code | 404, clear error |
| Expired code | 403, clear error |
| Redeemed code | 403, "already used" |
| Revoked code | 403, clear error |
| Suspended/cancelled license | 403, restriction message |
| Expired license | 403, restriction message |
| Inactive school | 403, restriction message |
| Valid code | continue |

Replay is rejected: the code is redeemed in the same transaction as account
creation (single-winner redeem), so a second attempt can never create a second
admin.

The school is **always** derived server-side from the code's license — a
client-supplied `school_id` is accepted for backward compatibility but never
trusted.

## Teacher entry (`/login`)

One shared login serving both audiences. The card explains the two paths:

- **School Teacher** — "Your school provides access."
- **Individual Teacher** — "Start free, or upgrade to Teacher Pro."

The Free vs Pro comparison card is included below the form; it explains
independent use so it does not confuse a school teacher whose school already
provides everything.

## Free individual teacher registration (`/signup`)

"Create Free Teacher Account" opens the individual registration flow: full
name, email, password, confirm password. No school is required. The server
creates:

- `role = teacher`
- `school_id = NULL`
- `subscription_type = "individual"`
- plan = **Free Teacher**

The client cannot choose role, plan, entitlement or `school_id` — those fields
are not part of the request model.

## Dashboard badge — who sees what

After login the teacher dashboard resolves the entitlement via
`GET /api/auth/my-plan` and shows the correct badge:

| Situation | Badge | Detail |
|---|---|---|
| School Teacher (active school entitlement) | **SCHOOL ACCESS** | School name + plan |
| Individual, no paid plan | **FREE TEACHER** | Individual plan |
| Individual Pro | **INDIVIDUAL TEACHER PRO** | Individual subscription |

A school teacher is **not** pushed toward buying Individual Pro — the upgrade
button only appears for an individual teacher on the free plan.

## Entitlement resolution

The backend remains authoritative. `resolve_entitlement(db, user)` returns one
dict describing the effective entitlement. Four states:

| State | Conditions | Result |
|---|---|---|
| A | teacher + `school_id` + active school entitlement | SCHOOL ACCESS |
| B | teacher + `school_id = NULL` + free individual | FREE TEACHER |
| C | teacher + `school_id = NULL` + active individual Pro | INDIVIDUAL PRO |
| D | teacher + school entitlement + individual Pro | most permissive **per capability** |

State D uses the existing documented rule: for each capability the *more*
permissive value wins (e.g. school may grant batch generation while individual
Pro grants higher AI credits). No new competing entitlement logic was added.

The resolution payload now includes `school_name` (set when access comes from
a school) so the frontend can render the SCHOOL ACCESS badge.

## Routes

| Group | Routes |
|---|---|
| Public | `/` |
| Platform | `/login/platform-admin`, `/platform-admin/*` |
| School | `/activate-school`, `/login/school-admin`, `/school-admin/*` |
| Teacher | `/login`, `/signup`, `/dashboard`, `/templates`, `/generate`, `/lessons`, `/settings`, `/upgrade` |

## Security boundaries

The public entry system does not weaken existing authorization. All checks are
backend dependencies; the browser role is never trusted.

| Attempt | Result |
|---|---|
| Teacher → Platform Admin route/API | denied (403) |
| Teacher → School Admin route/API | denied (403) |
| School Admin → Platform Admin | denied (403) |
| School Admin from another school | denied / scoped to own school |
| Unauthenticated → private route | redirected / 401 |
| Invalid activation code | rejected |
| Activation-code replay | rejected |
| Anonymous creating School Admin | rejected |
| Anonymous creating Free Teacher | allowed, only via `/register/individual` |

Platform Admin remains the only role that can create schools, create school
plans/licenses, generate activation codes, manage individual teacher
subscriptions, verify payments and view platform-wide commercial data. None of
those controls are exposed on public pages.

## Password UX

All login and registration forms retain the existing reusable components: the
password eye toggle (`PasswordInput`), accessible labels, live match indicator
(`PasswordMatchIndicator`), real email validation and the published password
policy (min 8 chars, letter + number + symbol). The authoritative rule is
served by `GET /api/auth/setup/status` under `password_policy` so the frontend
mirrors the backend exactly.

## Files

| File | Purpose |
|---|---|
| `frontend/src/app/page.tsx` | Public landing page (3 role cards) |
| `frontend/src/components/role-login.tsx` | Shared login form + teacher two-path note + activation link |
| `frontend/src/app/activate-school/page.tsx` | 4-step school activation |
| `frontend/src/app/signup/page.tsx` | Individual teacher registration |
| `frontend/src/app/dashboard/page.tsx` | SCHOOL ACCESS / FREE / PRO badge |
| `backend/src/routers/auth.py` | login, `/register/individual`, activation validate + redeem, `/my-plan` |
| `backend/src/entitlements.py` | `resolve_entitlement` (adds `school_name`) |
| `backend/src/auth.py` | `require_admin`, `require_platform_admin` guards |
| `backend/tests/test_public_entry_roles.py` | 40 tests for this layer |

## Tests

`test_public_entry_roles.py` covers: public/setup routes, individual
registration (forced role/school/plan), the shared teacher login for both
audiences, entitlement states A-D, activation validation/redeem/replay,
suspended licenses, wrong-role denial at the dependency level, cross-school
scoping, and password/email UX regression.
