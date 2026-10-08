# Production Version Check (Final Smoke Attempt)

Date: 2026-10-08 (retry)
Source (HEAD==origin/main): 9d7e401
Intended deployment: 50bd887 (docs-only diff to 9d7e401)
Deployed commit: UNKNOWN (no public deploy metadata). API healthy v1.0.5.

Registration: Public /signup reachable (200). Direct API self-registration attempted with synthetic email returned 500 (internal server error). Cannot establish authenticated session without credentials.

Marker expectation (current impl): topic/objective style per docs/benchmark/after.json (deterministic P2 form). Runtime marker comparison not executed (no auth).

Conclusion: Production build equivalence unconfirmed; P4 execution in production NOT EVIDENCED. Auth path blocked for automated smoke (requires valid registration/approval or existing credentials).
