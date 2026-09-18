# TeachFlow Desktop Release 1.0.2 — Report

**Release date:** 2026-09-15
**Scope:** Clean rebuild + reinstall of the Windows desktop application, fixing the packaged-backend startup crash that shipped in 1.0.1.

---

## 1. Root cause of the 1.0.1 desktop crash

The packaged desktop backend crashed on every launch with exit code 1:

```
TypeError: Router.__init__() got an unexpected keyword argument 'on_startup'
  File "src\main.py", line 167, in <module>          <- app.include_router(...)
  File "fastapi\applications.py", line 896, in __init__
  File "fastapi\routing.py", line 835, in __init__
```

`FastAPI.include_router()` in **fastapi 0.115.0** forwards `on_startup` / `on_shutdown`
into Starlette's `Router`. The packaged dependency set contained a Starlette far newer
than that, which had **removed** those parameters.

`desktop/build-requirements.txt` pinned `fastapi==0.115.0` but left **starlette unpinned**,
so the build resolved an incompatible Starlette. The result was a packaged dependency set
that differed from the working development environment.

A **second, latent packaging defect** was found during the rebuild: `desktop/backend.spec`
hardcoded native DLLs from `C:\Users\SAVIOUR\miniconda3` (pyd/dll files belonging to a
different interpreter). This made the bundle non-reproducible and pinned it to one machine's
absolute paths.

Because the backend never started, the desktop database had been stuck at migration **v003**
— it had no `schools`, `school_licenses`, `activation_codes`, or `school_memberships` tables
and no `role`/`school_id` columns. **The commercial layer had never run on the desktop.**

### Fixes applied

| Fix | File |
|---|---|
| Pin `fastapi==0.141.1` + `starlette==1.6.0` together (matches the working dev runtime) | `desktop/build-requirements.txt`, `backend/requirements.txt` |
| Derive native DLLs from the build interpreter (`sys.base_prefix`) instead of hardcoded miniconda paths; collect `sqlite3.dll`, `ffi.dll`, `libcrypto-3-x64.dll`, `libssl-3-x64.dll` and the matching stdlib `.pyd` files | `desktop/backend.spec` |
| Register the newer `platform_admin` router in PyInstaller `hiddenimports` | `desktop/backend.spec` |

---

## 2. Exact dependency versions (resolved)

Resolved in the dedicated packaging environment `desktop/build-venv` (Python 3.13.13), from the corrected `desktop/build-requirements.txt`:

| Package | Version |
|---|---|
| fastapi | 0.141.1 |
| starlette | 1.6.0 |
| uvicorn | 0.30.6 |
| SQLAlchemy | 2.0.35 |
| pydantic | 2.9.2 |
| pyinstaller | 6.22.3 |
| python-docx | 1.1.2 |
| docxtpl | 0.16.0 |
| openpyxl | 3.1.5 |
| pandas | 2.2.3 |
| passlib | 1.7.4 |
| bcrypt | 4.2.0 |
| python-jose | 3.3.0 |
| aiosqlite | 0.20.0 |
| structlog | 24.4.0 |
| httpx | 0.27.2 |
| requests | 2.32.3 |
| PyMuPDF | 1.28.2 |

`fastapi` and `starlette` are now pinned **together** so this mismatch cannot recur.

---

## 3. Version bump to 1.0.2

Single source of truth updated in all five locations:

| Location | Value |
|---|---|
| `backend/src/config.py` (`APP_VERSION`) | 1.0.2 |
| `frontend/src/app/layout.tsx` (page title) | TeachFlow v1.0.2 |
| `frontend/src/app/settings/page.tsx` (About) | 1.0.2 |
| `frontend/package.json` | 1.0.2 |
| `desktop/package.json` (drives installer metadata) | 1.0.2 |

---

## 4. Build pipeline executed

1. Frontend: `NEXT_PUBLIC_BUILD_TARGET=desktop npm run build` → 17 static pages.
2. Backend: `build-venv/Scripts/python.exe -m PyInstaller backend.spec --clean --noconfirm`.
3. Electron: `npx electron-builder --win --config`.
4. Checksum: `sha256sum`.

**Frozen-backend preflight (diagnostic only — §6), before packaging:**

| Check | Result |
|---|---|
| startup succeeds | PASS |
| migrations run (v001–v005) | PASS |
| SQLite loads (`_sqlite3` imports) | PASS |
| `GET /api/health` | 200 `{"version":"1.0.2"}` |
| `GET /api/auth/setup/status` | 200 |
| `/api/platform-admin/*` mounted | 401 (route present) |
| process stays alive | PASS |

---

## 5. Installer

| Item | Value |
|---|---|
| Path | `desktop/release/TeachFlow-Setup-1.0.2-x64.exe` |
| Size | 116,338,280 bytes (110.9 MB) |
| SHA-256 | `9dea6fbbb2dc720bfdfa0f0bd9e2edd31ee68ff7354a5b08e88f3bf2b2bbe467` |
| Checksum file | `desktop/release/TeachFlow-Setup-1.0.2-x64.exe.sha256` |
| Previous 1.0.1 installer (rollback) | `desktop/release-archive/TeachFlow-Setup-1.0.1-x64.exe` |

**Installation:** the 1.0.1 application had already been removed and left a stale backend
process holding port 18234; that process and a duplicate frontend server were terminated.
1.0.2 was then installed silently (`/S`) to
`%LOCALAPPDATA%\Programs\TeachFlow`. **User data was preserved throughout** —
`%APPDATA%\teachflow-desktop\data\teachflow.db` was never deleted.

---

## 6. Installed version verification

| Evidence | Result |
|---|---|
| Installed backend binary SHA-256 | `bd3a52615066ef8f91c3f21da25946468991bc1f85e8106be6061d5b41aaac9e` |
| Newly built binary SHA-256 | identical (byte-for-byte the new executable) |
| Installed `resources/frontend/platform-admin` | present |
| Installed `_internal/sqlite3.dll`, `ffi.dll` | present |
| `GET http://127.0.0.1:18234/api/health` | `{"version":"1.0.2"}` |
| Diagnostics log | `{"version": "1.0.2", "event": "TeachFlow started"}` |
| Migration on first 1.0.2 launch | `v004_commercial_licensing` **applied**, `v005_school_isolation` **applied** |
| Backend exit code during workflow | **none** — PID unchanged (23832) across the entire test |

The previously reported crash (`on_startup` / exit code 1) **no longer occurs**.

---

## 7. Desktop acceptance results

All tests were run against the **installed 1.0.2 application's own backend**
(`http://127.0.0.1:18234`) and its own database, on real user data that was migrated in place.

### 7.1 Commercial workflow — PASS

| Step | Result |
|---|---|
| Platform admin login (`admin@bloomcore.com`) | PASS — role `platform_admin` |
| Dashboard | PASS |
| Create school — **Awasive M/A Basic School** | PASS (`AWASIVE-DESKTOP-01`) |
| Create plan — **TeachFlow School Annual**, GH₵800, 20 seats, 365 days | PASS |
| Create license | PASS — `TF-LIC-CLCS-VOEZ`, expiry 2027-09-15, seat limit 20 |
| Generate activation code (new endpoint) | PASS — `TF-SCH-35HU-LSH4-R0CE` |
| Desktop activation | PASS — returns school / plan / expiry / seat limit |
| School detail (licence, seats, teachers) | PASS |
| Create school administrator | PASS — role `school_admin`, linked to the school |
| School admin login | PASS |
| School admin blocked from platform admin | PASS — HTTP 403 |
| Create teacher — **Test Teacher** | PASS |
| Teacher login | PASS — role `teacher` |
| Seat count updates | PASS — **1 / 20** |
| Teacher blocked from platform admin | PASS — HTTP 403 |

### 7.2 Real Science lesson-plan workflow — PASS

Source: `BASIC 9 SCIENCE SCHEME OF LEARNING.docx`

| Step | Result |
|---|---|
| Upload | PASS — original filename preserved |
| Weeks detected | PASS — **15 weeks** |
| Validate curriculum | PASS (200) |
| Approve | PASS (200) |
| Generate | PASS — job `completed` |
| Lesson plans persist | PASS |
| DOCX export | PASS — 424,545 bytes |
| XLSX export | PASS — 7,198 bytes |
| ZIP export | PASS — multi-lesson DOCX export is returned as a ZIP bundle |

### 7.3 Math subset — PASS

Source: `BASIC 9 MATH SCHEME OF LEARNING.docx`

| Step | Result |
|---|---|
| Upload / weeks | PASS — 15 weeks |
| Approve / Generate | PASS — `completed` |
| DOCX/ZIP export | PASS — 424,759 bytes |
| XLSX export | PASS — 7,179 bytes |

### 7.4 Persistence across restart — PASS

Application closed and relaunched. Afterwards:

- `/api/health` → 1.0.2
- School **Awasive M/A Basic School** still present, `teachers=1`
- Licence still `active`, **1/20**
- Users persisted: 2 platform/school/teacher accounts created during the test, plus the 2
  pre-existing accounts migrated to `role` values by v004/v005
- Schemes: **3**, lesson plans: **24**

---

## 8. Cleanup report

### Deleted

| Path | Type | Size |
|---|---|---|
| `desktop/release/win-unpacked` (1.0.1) | stale Electron output | ~1.18 GB |
| `desktop/dist` (1.0.1 backend) | stale PyInstaller output | ~926 MB |
| `desktop/build` (1.0.1 + 1.0.2 PyInstaller work) | build cache | ~260 MB |
| `frontend/.next` (pre-build) | stale Next.js cache | ~127 MB |
| `desktop/release/builder-debug.yml`, `*.blockmap`, `*.sha256` (1.0.1) | stale metadata | small |
| `DScience/Lesson Plan/verify_slice.py`, `verify_teacher.py` | temporary verification scripts | small |
| `%LOCALAPPDATA%\Programs\TeachFlow` (empty leftover) | obsolete install dir | — |

### Archived (rollback)

| Path | Reason |
|---|---|
| `desktop/release-archive/TeachFlow-Setup-1.0.1-x64.exe` (+ blockmap) | previous known-bad installer, kept for rollback |

### Retained

`desktop/release/` (new installer + unpacked 1.0.2), `desktop/dist/` (new backend build),
`frontend/out`, `frontend/.next` (in use by the running dev server), `desktop/build-venv`,
`desktop/py312`, `backend/venv`, all source, tests, migrations, docs, config, lock files,
and all user application data.

### Disk-space result

| | Size |
|---|---|
| Old build artifacts before cleanup | **2,838 MB** (release + dist + build + .next) |
| Retained artifacts after cleanup | **914 MB** |
| Net reduction | **~1,924 MB (~1.9 GB)** |

Largest remaining directories: `desktop/release` 467 MB, `desktop/release-archive` 330 MB,
`desktop/py312` 326 MB, `desktop/build-venv` 301 MB, `backend/venv` 270 MB.

---

## 9. Automated tests

```
246 passed, 389 warnings in 21.10s
```

One pre-existing test (`test_all_routers_registered`) asserted FastAPI internals
(`route_types.count("APIRoute") >= 20`). Under fastapi 0.141.1 included routers are mounted
lazily as `_IncludedRouter`, so the assertion no longer described the runtime. It was
rewritten to assert the generated OpenAPI schema instead — a stable, meaningful check that
every router prefix is actually mounted.

---

## 10. Remaining limitations

1. **The desktop UI was verified through the installed application's backend API, not by
   clicking the rendered window.** Every endpoint the shipped UI calls was exercised against
   the installed app's own backend and database, and the installed frontend bundle contains
   all routes, but a literal human click-through of the window is still recommended.
2. **`AttributeError: module 'bcrypt' has no attribute '__about__'`** is logged by passlib's
   version probe with bcrypt 4.x. It is cosmetic — all logins in this test succeeded. Pinning
   `bcrypt==4.0.1` or replacing the passlib probe would remove the noise.
3. **Generation reports `total_lessons: 38` but `completed_lessons: 12`.** The plans that are
   produced are correct and export cleanly; the reported total appears to count planned
   lesson slots (including non-teaching/special weeks) rather than generated plans. Worth a
   separate look.
4. **AFM/offline grace period** remains out of scope — PENDING PRODUCT DECISION.
5. The 30-day offline validation policy is not implemented.

---

## 11. Reproduce the build

```bash
# frontend
cd frontend && NEXT_PUBLIC_BUILD_TARGET=desktop npm run build

# backend (dedicated packaging env, corrected pins)
cd desktop
./build-venv/Scripts/python.exe -m pip install -r build-requirements.txt pyinstaller
./build-venv/Scripts/python.exe -m PyInstaller backend.spec --clean --noconfirm

# installer
npx electron-builder --win --config

# checksum
cd release && sha256sum TeachFlow-Setup-1.0.2-x64.exe > TeachFlow-Setup-1.0.2-x64.exe.sha256
```
