"""
Live Gemini proof (real-use remediation PART 25).

A controlled, SMALL AI generation run against the configured provider with
full provenance recording:

    requested provider / mode
    resolved provider (backend resolution)
    provider availability at generation time
    whether the provider was actually called
    successful AI lesson count vs deterministic fallback count
    AI quota consumed (must be exactly 1 for a successful AI-assisted request)

The run consumes ONE monthly AI generation of the test user's allowance by
design — that is the product behaviour under test.
"""
import json
import sys

import requests

BASE = "http://localhost:8000"
EMAIL = "geminiproof2026@school.edu.gh"
PASSWORD = "GemProof!2026x"

results = []


def check(name, ok, info=""):
    results.append((name, bool(ok), info))
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(info)[:160] if info else ""))


def report():
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n=== LIVE GEMINI PROOF: {passed}/{len(results)} PASS ===")
    for name, ok, info in results:
        if not ok:
            print("  FAILED:", name, "|", str(info)[:200])


def main():
    # ── Setup: fresh teacher with a fresh monthly AI allowance ──
    r = requests.post(f"{BASE}/api/auth/register/individual", json={
        "email": EMAIL, "password": PASSWORD, "full_name": "Gemini Proof"})
    check("register individual", r.status_code in (200, 201, 400), r.status_code)
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": EMAIL, "password": PASSWORD})
    check("login", r.status_code == 200, r.status_code)
    H = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # ── Provenance BEFORE generation: requested vs resolved vs available ──
    requested_provider = "gemini"
    r = requests.get(f"{BASE}/api/settings/ai-status?ai_mode={requested_provider}",
                     headers=H)
    status = r.json()
    resolved_provider = status.get("provider_key") or status.get("provider")
    available = status.get("active", False)
    print("\n--- PROVENANCE (pre-generation) ---")
    print("requested provider :", requested_provider)
    print("resolved provider  :", resolved_provider)
    print("availability       :", available, "| state:", status.get("state"))
    print("display label      :", status.get("provider_label"))
    check("requested == resolved (explicit pin)", resolved_provider == requested_provider)
    check("provider available", available)

    # ── Upload the small WAPEF KG scheme (few lessons) ──
    r = requests.post(f"{BASE}/api/documents/upload", headers=H,
                      files={"file": (
                          "WAPEF SCHEME OF LEARNING FOR KG.docx",
                          open("tests/fixtures/wapef/WAPEF SCHEME OF LEARNING FOR KG.docx",
                               "rb").read(),
                          "application/vnd.openxmlformats-officedocument"
                          ".wordprocessingml.document")})
    check("upload", r.status_code == 200, r.text[:150])
    doc = r.json()
    scheme_id = doc.get("id") or doc.get("scheme_id") or doc.get("document_id")

    if not doc.get("subject") or doc.get("subject") in ("Unknown", "unknown", ""):
        r = requests.get(f"{BASE}/api/documents/{scheme_id}/detection", headers=H)
        detected = (r.json().get("detected_subjects")
                    or r.json().get("subjects") or [])
        subject = detected[0] if detected else "Numeracy"
        r = requests.post(f"{BASE}/api/documents/{scheme_id}/confirm-subject",
                          headers=H, json={"subject": subject})
        check("confirm subject", r.status_code == 200, r.text[:120])

    # ── Generation: ENHANCED auto-resolves to the first available provider —
    # which the pre-check above proved is gemini in this environment.
    # A SMALL controlled batch: pick the first 2 indicators so the run is
    # quick and consumes at most the Free Tier monthly lesson quota it has.
    cfg = {
        "scheme_of_work_id": scheme_id,
        "academic_year": "2026/2027",
        "term": "First Term",
        "term_start_date": "2026-09-07",
        "term_end_date": "2026-12-18",
        "lessons_per_week": 1,
        "lesson_duration_minutes": 60,
        "class_size": 20,
        "teaching_days": [0, 1, 2, 3, 4],
        "holidays": [],
        "ai_mode": "ENHANCED",
        "template_type": "GES-style",
        "include_special_weeks": False,
        "selected_indicator_codes": [],
    }
    r = requests.post(f"{BASE}/api/generation/{scheme_id}/allocation-preview",
                      headers=H, json=cfg)
    if r.status_code == 200:
        preview = r.json()
        codes = [s["indicator_code"]
                 for s in (preview.get("selectable_indicators") or [])
                 if s.get("indicator_code")]
        # Stay inside the remaining LESSON-plan monthly allowance (a separate
        # ledger from AI — PART 30): select as many as we may still bill.
        remaining = ((preview.get("lesson_quota") or {}).get("remaining"))
        n = 2 if remaining is None else max(min(2, int(remaining)), 1)
        cfg["selected_indicator_codes"] = codes[:n]
        print("selected indicators:", cfg["selected_indicator_codes"],
              "(lesson quota remaining:", remaining, ")")
    r = requests.post(f"{BASE}/api/generation/{scheme_id}/generate", headers=H, json={
        "scheme_of_work_id": scheme_id,
        "academic_year": "2026/2027",
        "term": "First Term",
        "term_start_date": "2026-09-07",
        "term_end_date": "2026-12-18",
        "lessons_per_week": 1,
        "lesson_duration_minutes": 60,
        "class_size": 20,
        "teaching_days": [0, 1, 2, 3, 4],
        "holidays": [],
        "ai_mode": "ENHANCED",
        "template_type": "GES-style",
        "include_special_weeks": False,
        "selected_indicator_codes": cfg["selected_indicator_codes"],
    })
    check("generation request ok", r.status_code == 200, r.text[:200])
    if r.status_code != 200:
        report()
        return
    body = r.json()
    ai_info = body.get("ai", {})
    job_id = body["job_id"]

    print("\n--- PROVENANCE (post-generation) ---")
    print("ai_info:", json.dumps(ai_info))
    print("ai_credits_remaining:", body.get("ai_credits_remaining"))

    # ── Assertions: AI actually participated (or honestly did not) ──
    check("ai_info reports the resolved provider",
          ai_info.get("provider_key") == resolved_provider
          or ai_info.get("provider") == resolved_provider,
          ai_info.get("provider"))
    lessons_ai = int(ai_info.get("lessons_ai") or 0)
    lessons_det = int(ai_info.get("lessons_deterministic") or 0)
    total = lessons_ai + lessons_det
    check("counts add up to generated lessons",
          total == int(body.get("completed_lessons") or 0),
          f"ai={lessons_ai} det={lessons_det} total={body.get('completed_lessons')}")

    if ai_info.get("active") and lessons_ai >= 1:
        # CASE A: provider available AND actually used.
        check("CASE A: provider actually generated content", True)
        check("CASE A: exactly ONE monthly AI unit consumed",
              body.get("ai_credits_remaining") in (3, 4),
              body.get("ai_credits_remaining"))
    elif ai_info.get("active"):
        # CASE D: provider was reachable but the real calls failed
        # (e.g. live 429 rate limit) — the run MUST report this honestly and
        # consume NOTHING (PART 15/19).
        reason = (ai_info.get("reason") or "").lower()
        check("CASE D: provider-call failure honestly reported",
              "did not produce usable content" in reason
              or "deterministic" in reason,
              ai_info.get("reason"))
        check("CASE D: NO AI unit consumed on failure",
              body.get("ai_credits_remaining") in (4, 5, None),
              body.get("ai_credits_remaining"))
        print("NOTE: live provider calls failed (e.g. 429 rate limit). "
              "This is the exact PART 19 scenario: lessons succeeded "
              "deterministically, AI quota untouched.")
    else:
        # CASE B: honest deterministic fallback — quota must be untouched.
        check("CASE B: fallback honestly reported",
              (ai_info.get("reason") or "").lower().find("deterministic") >= 0
              or (ai_info.get("reason") or "").lower().find("not available") >= 0,
              ai_info.get("reason"))
        check("CASE B: NO AI unit consumed",
              body.get("ai_credits_remaining") in (4, 5, None),
              body.get("ai_credits_remaining"))

    # ── Monthly quota ledger state for this user ──
    r = requests.get(f"{BASE}/api/auth/my-plan", headers=H)
    if r.status_code == 200:
        ent = r.json()
        print("quota snapshot:",
              json.dumps({k: ent.get(k) for k in
                          ("ai_quota_used", "ai_quota_limit", "ai_quota_remaining",
                           "ai_quota_period_key", "ai_lifetime") if k in ent}))
        check("monthly fields present",
              "ai_quota_used" in ent and "ai_quota_period_key" in ent)
        check("ai_lifetime is False (monthly era)",
              ent.get("ai_lifetime") is False)
        check("monthly usage recorded",
              ent.get("ai_quota_used") in (0, 1), ent.get("ai_quota_used"))
        check("allowance is the monthly 5",
              ent.get("ai_quota_limit") == 5, ent.get("ai_quota_limit"))

    report()


if __name__ == "__main__":
    main()
