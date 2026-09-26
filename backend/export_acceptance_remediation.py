"""
Export acceptance (Parts AC/N/O): register a teacher, upload the real WAPEF
JHS-style scheme with a MID-TERM week, generate a normal lesson, verify
per-lesson metadata defaults and empty-field contract in the exported DOCX.

Run:  ./venv/Scripts/python.exe export_acceptance_remediation.py
"""
import io
import json
import re
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, ".")

from fastapi.testclient import TestClient  # noqa: E402
from src.main import app  # noqa: E402

client = TestClient(app)
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def main():
    import uuid
    email = f"expacc{uuid.uuid4().hex[:8]}@school.edu.gh"
    password = "AccTest!2026x"

    r = client.post(
        "/api/auth/register/individual",
        json={"email": email, "password": password, "full_name": "Export Acceptance"},
    )
    check("register teacher", r.status_code in (200, 201), r.text[:120])

    r = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    check("login teacher", r.status_code == 200, r.text[:120])
    token = r.json()["access_token"]
    H = {"Authorization": f"Bearer {token}"}

    # ── Template catalog (PART A/B/C) ──
    r = client.get("/api/templates/", headers=H)
    data = r.json()
    names = [t["name"] for t in data["templates"]]
    ids = [t["id"] for t in data["templates"]]
    check("templates listed", r.status_code == 200 and len(data["templates"]) >= 6,
          f"count={len(data['templates'])}")
    check("GES name present", any("GES" in n for n in names), str(names))
    check("WAPEF names present", sum(1 for n in names if "WAPEF" in n) >= 2)
    check("headteacher retired", "tpl-approved-org-headteacher" not in ids)
    check("no Headteacher wording",
          not any("Headteacher" in n for n in names))

    # ── Upload a scheme that contains a MID-TERM week ──
    scheme_docx = "tests/fixtures/wapef/WAPEF SCHEME OF LEARNING FOR NURSERY.docx"
    with open(scheme_docx, "rb") as f:
        content = f.read()
    r = client.post(
        "/api/documents/upload",
        files={"file": ("WAPEF SCHEME OF LEARNING FOR NURSERY.docx", io.BytesIO(content),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        headers=H,
    )
    if r.status_code not in (200, 201):
        # try alternate endpoint
        r = client.post(
            "/api/schemes/upload",
            files={"file": ("scheme.docx", io.BytesIO(content),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            headers=H,
        )
    check("scheme uploaded", r.status_code in (200, 201), f"{r.status_code} {r.text[:150]}")
    scheme = r.json()
    scheme_id = scheme.get("id") or scheme.get("scheme_id")

    # Multi-subject document: confirm a subject section (production flow §4).
    r = client.get(f"/api/documents/{scheme_id}/detection", headers=H)
    if r.status_code == 200:
        detected = r.json().get("detected_subjects") or []
        if detected:
            r2 = client.post(
                f"/api/documents/{scheme_id}/confirm-subject",
                headers=H, json={"subject": detected[0]},
            )
            check("subject section confirmed", r2.status_code == 200, r2.text[:120])

    if not scheme_id:
        check("scheme id returned", False, json.dumps(scheme)[:200])
        report()
        return

    # Confirm single subject if needed
    r = client.get(f"/api/schemes/{scheme_id}", headers=H)
    if r.status_code == 200:
        sdata = r.json()
        weeks = sdata.get("weeks") or []
        midterm = [w for w in weeks if "MID-TERM" in json.dumps(w).upper()]
        check("MID-TERM week present in source", len(midterm) >= 1)

    # ── Allocation preview: special periods must NOT count as lessons ──
    r = client.post(
        f"/api/generation/{scheme_id}/allocation-preview",
        headers=H,
        json={
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
            "ai_mode": "OFF",
            "template_type": "GES-style",
            "include_special_weeks": False,
            "selected_indicator_codes": [],
        },
    )
    check("allocation preview ok", r.status_code == 200, r.text[:150])
    if r.status_code == 200:
        preview = r.json()
        blob = json.dumps(preview)
        check("no MID-TERM string in lesson_review fields",
              "MID-TERM" not in json.dumps(preview.get("lesson_review", [])))

    # ── Generate ──
    r = client.post(
        f"/api/generation/{scheme_id}/generate",
        headers=H,
        json={
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
            "ai_mode": "OFF",
            "template_type": "GES-style",
            "include_special_weeks": False,
            "selected_indicator_codes": [],
        },
    )
    check("generation ok", r.status_code == 200, r.text[:200])
    if r.status_code != 200:
        report()
        return
    job_id = r.json()["job_id"]
    ai_info = r.json().get("ai", {})
    check("ai info reports resolved provider consistently",
          ai_info.get("provider") == ai_info.get("provider_key") or ai_info.get("provider") is None,
          json.dumps(ai_info)[:150])

    r = client.get(f"/api/generation/{job_id}/lessons", headers=H)
    lessons = r.json()["lesson_plans"]
    check("lessons generated", len(lessons) >= 1, f"count={len(lessons)}")

    for lp in lessons:
        blob = json.dumps(lp, default=str)
        check(f"lesson {lp.get('lesson_sequence')}: no MID-TERM leakage",
              "MID-TERM" not in blob.upper() or lp.get("special_period_label"),
              "")
        check(f"lesson {lp.get('lesson_sequence')}: no fake objective",
              "Learners can MID" not in blob)
        check(f"lesson {lp.get('lesson_sequence')}: other_tlrs empty by default",
              lp.get("other_tlrs") == [])
        check(f"lesson {lp.get('lesson_sequence')}: references empty by default",
              not lp.get("references") and not lp.get("structured_references"))
        check(f"lesson {lp.get('lesson_sequence')}: period empty or teacher-set",
              lp.get("period") in ("", None) or "Period" not in str(lp.get("period")))
        check(f"lesson {lp.get('lesson_sequence')}: keywords per-lesson (non-empty)",
              len(lp.get("keywords") or []) > 0, str(lp.get("keywords"))[:80])
        check(f"lesson {lp.get('lesson_sequence')}: competencies targeted",
              0 < len(lp.get("core_competencies") or []) <= 4)

    # Distinct lessons must not share an identical keyword list
    kw_lists = [tuple(sorted(l.get("keywords") or [])) for l in lessons]
    if len(kw_lists) > 1:
        check("keywords differ across lessons (per-lesson derivation)",
              len(set(kw_lists)) > 1)

    # ── Export DOCX (PART AC) ──
    r = client.post(
        f"/api/generation/{job_id}/export/docx?template_type=GES-style",
        headers=H,
    )
    check("docx export ok", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
    if r.status_code == 200:
        blob = r.content
        check("docx has content", len(blob) > 10000, f"size={len(blob)}")
        # extract document.xml and check placeholders
        try:
            z = zipfile.ZipFile(io.BytesIO(blob))
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
            text = re.sub(r"<[^>]+>", "", xml)
            check("no MID-TERM in export text", "MID-TERM" not in text.upper())
            check("no placeholder tokens left",
                  not re.search(r"\[[A-Z_]{4,}\]", text))
        except zipfile.BadZipFile:
            check("docx is valid zip", False)

    report()


def report():
    fails = 0
    print("\n=== EXPORT ACCEPTANCE RESULTS ===")
    for name, ok, detail in RESULTS:
        mark = "PASS" if ok else "FAIL"
        if not ok:
            fails += 1
        print(f"{mark} {name} {detail}")
    print(f"=== {len(RESULTS) - fails} passed, {fails} failed ===")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
