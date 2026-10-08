# Production Version Check

Date: 2026-10-08 (session)
Time (execution): ~completion time

SOURCE COMMIT (HEAD==origin/main): ae84f19
ORIGIN COMMIT: ae84f19140d35af06e274e592d1023ba71345477
ACTUAL DEPLOYED PRODUCTION COMMIT: UNKNOWN (not exposed via public endpoints)

API HEALTH: https://schemeknit-api.onrender.com/api/health -> {"status":"healthy","service":"SchemeKnit","version":"1.0.5"}
API DOCS: 404 (no /docs, /openapi.json, /api/docs exposed)
FRONTEND: https://schemeknit-frontend.onrender.com -> CDN/Next.js live (x-render-origin-server: Render, x-nextjs-cache: HIT)

EVIDENCE:
- P4 code present locally at ae84f19 (lesson_quality_gate.py, ledger wiring in routers/generation.py + allocation_engine.py + generation_pipeline.py)
- Marker driver previously confirmed production stale vs local (2026-10-08). No post-deploy verification possible without Render logs/owner access.

BLOCKER: Owner-side Render deployment verification required. Cannot confirm production serves ae84f19 / P4.

DEPLOYMENT HANDOFF (for owner):
- Required commit: ae84f19 (origin/main)
- Current deployed commit: UNKNOWN
- Action: Confirm Render deploy completed (push to main triggered) and smoke-test production after deploy.
- Verification: GET /api/health (200), run minimal production smoke (auth/upload/extraction/generate Autopilot AI-OFF, DOCX/PDF, reload). Also verify quality gate behavior with a normal scheme.
- Expected: production behavior consistent with local (P4 gate active; no quota bypass; accept-only persist).
