# Production Version Check (Post-Redeployment)

Date: 2026-10-08 23:43 UTC

SOURCE (HEAD==origin/main): 50bd8872e2fe73c5e4b459b37ab94bf233434e88
INTENDED DEPLOYMENT: 50bd887 (current)

ACTUAL DEPLOYED COMMIT: UNKNOWN (no public deploy metadata)
- API: https://schemeknit-api.onrender.com/api/health -> 200 {"status":"healthy","service":"SchemeKnit","version":"1.0.5"}
- Frontend: https://schemeknit-frontend.onrender.com -> 200 (Render origin)

BUILD EQUIVALENCE: CANNOT BE PROVEN from public endpoints. Redeployment reported complete; no commit SHA exposed. Deterministic marker is the only runtime evidence of build equivalence.

RUNTIME EVIDENCE REQUIRED: Production smoke (auth/upload/detection/Autopilot AI-OFF/generate) must demonstrate current deterministic behavior (P2/P4). Without executing that journey, equivalence remains unconfirmed.
