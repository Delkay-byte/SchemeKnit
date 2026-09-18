# TeachFlow UX Workflow Audit — v1.0.1 (Updated 2026-09-15)

## Summary

This document records the UX/workflow remediation completed for TeachFlow v1.0.1.
The goal was to transform TeachFlow from a collection of backend features into a
coherent product that a Ghanaian teacher can understand on first use.

---

## Phase 1 Changes (Original)

### 1. Shared Navigation Header (`src/components/header.tsx`)
- Single shared `Header` component used by all authenticated pages
- Dashboard, Upload, Lesson Plans, Templates navigation links
- Admin link (only visible for admin users via `user.is_admin`)
- Settings gear icon + Logout button
- Active page highlighting
- Responsive (mobile-friendly)

### 2. Dashboard (`src/app/dashboard/page.tsx`)
- Workflow summary showing 5-step process
- **Clickable** Pending Review card → navigates to first pending scheme review
- **Clickable** Ready to Generate card → navigates to first approved scheme generate page
- Quick Actions: Upload Scheme, Lesson Plans, Templates, Admin (admin only)
- Settings REMOVED from Quick Actions (already in header)
- Schemes list with original filenames and status badges

### 3. Upload Page (`src/app/upload/page.tsx`)
- Drag-and-drop file upload
- Progress bar during upload
- Success card with "Review Curriculum" CTA → navigates to `/review/{scheme_id}`
- "What happens next?" guide

### 4. Review Page (`src/app/review/[id]/page.tsx`)
- Week sidebar with type badges (Instruction, Revision, Assessment, etc.)
- Week detail view with strand, sub-strand, content standards, indicators
- "Approve & Generate Lesson Plans" CTA

### 5. Login Page (`src/app/login/page.tsx`)
- Title: "Sign in to TeachFlow"
- Description: "Use the email and password provided by your TeachFlow administrator."
- No role selector (roles determined by system)
- Setup wizard check (redirects to /setup if no users exist)

---

## Phase 2 Changes (Current — Functional Flow Fixes)

### 6. Backend Crash Fix (`backend/src/routers/documents.py`)
**Root Cause:** 9 bugs identified in the upload flow:
- BUG #1 (CRITICAL): Missing `TemplateType` import in service.py → NameError during generation
- BUG #2 (CRITICAL): File write outside try/except → unhandled OSError
- BUG #3 (HIGH): Synchronous blocking I/O in async handler → event loop starvation → process killed
- BUG #4 (HIGH): Validation issues hardcoded to `[]` → data loss
- BUG #5 (HIGH): Relative upload directory → files written to wrong location
- BUG #6 (MEDIUM): PDF accepted but DOCX parser can't handle it
- BUG #7 (MEDIUM): No database rollback on failed commit
- BUG #8 (LOW): No cleanup of uploaded files on parse failure
- BUG #9 (LOW): Entire file loaded into memory before size check

**Fixes Applied:**
- Added `TemplateType` import to service.py
- Moved file write inside try/except with cleanup
- Used `run_in_executor` for blocking I/O (file write, Document parsing)
- Store validation issues: `[vi.model_dump() for vi in scheme.validation_issues]`
- Absolute upload directory via `TEACHFLOW_DATA_DIR` env var
- Removed PDF from allowed extensions (only .docx)
- Added `db.rollback()` in `get_db()` exception handler
- File cleanup on parse failure: `file_path.unlink()`
- Stream-read file in 8KB chunks before size check

### 7. Dashboard Navigation Fix (`frontend/src/app/dashboard/page.tsx`)
**Problem:** "Pending Review" and "Ready to Generate" cards were NOT wrapped in `<Link>` components.

**Fix:**
- Pending Review card → `<Link href={`/review/${pendingSchemes[0].id}`}>`
- Ready to Generate card → `<Link href={`/generate/${approvedSchemes[0].id}`}>`
- When count = 0, cards are disabled (opacity-60, no link)

### 8. Settings Removed from Quick Actions
**Problem:** Settings appeared as a Quick Action card despite already being in the header.

**Fix:** Removed Settings card. Quick Actions now show:
- Upload Scheme
- Lesson Plans
- Templates
- Admin (admin only)

### 9. Lesson Plans Workspace (`frontend/src/app/lessons/page.tsx`)
**Problem:** No dedicated page to view all generated lesson plans.

**Fix:**
- Created `/lessons` page
- Table view: Week, Lesson, Date, Topic, Scheme, Status, Actions
- Filter by scheme (when multiple schemes exist)
- View/Edit actions link to generate page
- Empty state with "Go to Dashboard" CTA
- Added `GET /api/generation/lessons` backend endpoint
- Added `listAllLessons()` to frontend API service

### 10. Header Updated (`frontend/src/components/header.tsx`)
- Added "Lesson Plans" link to navigation
- Admin link gated by `user.is_admin`

### 11. Upload Page Fixes (`frontend/src/app/upload/page.tsx`)
- Fixed review button: `result.scheme_id` (was `result.id`)
- Removed PDF from accepted file types
- Updated descriptions to say ".docx only"

### 12. Original Filenames Display
- Dashboard: `<h4 className="font-semibold truncate">{scheme.filename}</h4>`
- Review page: `<h2 className="text-lg font-semibold">{scheme.filename}</h2>`
- Upload success: `{result.filename || file?.name}`
- Backend stores original filename in `SchemeDB.filename`

### 13. Currency (GH₵)
- `formatCurrency()` in `utils-display.ts` returns `GH₵ X.XX`
- Used in: Admin page, Payments page, Payment history
- No `$` anywhere in the frontend

### 14. Version Consistency
- `desktop/package.json`: "version": "1.0.1"
- `backend/src/config.py`: APP_VERSION = "1.0.1"
- `frontend/src/app/layout.tsx`: "TeachFlow v1.0.1"
- `frontend/src/app/settings/page.tsx`: "Version: 1.0.1"

### 15. Admin/Teacher Role Separation
- Backend: `is_admin` boolean on User model
- First user (setup): `is_admin=True` (School Administrator)
- Created users: `is_admin=False` (Teacher)
- Frontend: Admin link, Admin card, Admin page gated by `user.is_admin`
- Non-admin redirected from `/admin` to `/dashboard`
- No role selector in login or setup

---

## Commercial Ownership Architecture (Documented, Not Yet Implemented)

### Data Model Design
```
PlatformOwner (BloomCore/TeachFlow)
├── manages: Schools
│   ├── SchoolAdministrator (per school)
│   │   ├── creates: Teachers (seat-based)
│   │   └── manages: school workspace
│   └── subscription: SchoolLicense
│       ├── license_code
│       ├── teacher_seats
│       ├── expiry_date
│       └── features
└── manages: GlobalSettings
    ├── pricing
    ├── content_packs
    ├── templates
    └── payments
```

### Free Offline Core
- Deterministic lesson-plan generator works without subscription/internet
- Licensed premium features are entitlement-controlled

### Commercial Tiers
1. FREE OFFLINE — Basic generation, no account needed
2. INDIVIDUAL TEACHER PRO — Single teacher, premium templates
3. SCHOOL LICENSE — Multi-teacher, admin dashboard
4. CONTENT PACK PURCHASE — Additional curriculum content
5. CUSTOM GENERATION SERVICE — Bespoke lesson plans

---

## Remaining Deferred Items

| Item | Priority | Status |
|------|----------|--------|
| Sample template upload & mapping | Medium | Architecture designed, implementation deferred |
| Commercial licensing activation | Medium | Data model documented, integration deferred |
| Real-time generation progress | Low | WebSocket/polling not yet implemented |

---

## Build Information

- **Installer:** `desktop/release/TeachFlow-Setup-1.0.1-x64.exe`
- **Frontend Pages:** 15 (including new `/lessons` page)
- **Backend Endpoints:** All functional, crash fixes applied
- **Database:** SQLite, 3 migrations applied
- **User Data Path:** `%APPDATA%/teachflow-desktop/data/teachflow.db`
