"""Priority 3.1 — Autopilot (zero-decision) generation test matrix (§22).

A. All data confidently detected            → one-click Autopilot selection ready
B. 17 pending, 5 quota                      → automatically selects 5
C. 17 pending, unlimited                    → automatically selects all
D. 4 pending, 10 quota                      → automatically selects all 4
E. Needs-review rows                        → only safe occurrences selected
F. WAPEF with saved values                  → auto-generates (no blocker)
G. WAPEF without saved values               → ONLY the WAPEF input blocks
H. Repeated indicator across weeks          → two distinct occurrences, one unit
I. Special-only week                        → ignored (never generates)
J. Partial generation                       → failed/unstarted stay pending (resume)
K. Quota exhausted                          → clear message, no job created
L. Deterministic generation                 → AI stays OFF by default
M. Manual mode                              → unchanged (pinned by the P3 suite)

The pure rules live in ``src.engines.autopilot``; the endpoint tests run the
same rules through the real API the browser calls.
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database import EntitlementDB, SchemeDB, WeekDB, generate_id  # noqa: E402
from src.engines.autopilot import (  # noqa: E402
    select_autopilot_rows, selection_blockers, wapef_autopilot_state,
)
from src.models import TermConfig  # noqa: E402
from tests.conftest import make_user  # noqa: E402


# ── Pure rules ───────────────────────────────────────────────────────────────

def _row(week, code, occ=None, needs_review=False, special=False):
    return {
        "source_occurrence_id": occ or f"week{week}:0:{code}",
        "indicator_code": code,
        "needs_review": needs_review,
        "is_special_period": special,
        "week_number": week,
    }


def _select(rows, remaining=5, unlimited=False, enforced=True, indicatorless=False, generated=()):
    return select_autopilot_rows(
        rows,
        generated_ids=generated,
        quota_remaining=remaining,
        quota_unlimited=unlimited,
        quota_enforced=enforced,
        indicatorless=indicatorless,
    )


class TestPureSelection:
    def test_matrix_b_17_pending_5_quota_selects_exactly_5(self):
        rows = [_row(w, f"B7.1.1.{w}.1") for w in range(1, 18)]
        sel = _select(rows, remaining=5)
        assert sel["selected_count"] == 5
        assert sel["selected_indicator_codes"] == [
            f"B7.1.1.{w}.1" for w in range(1, 6)
        ]
        assert len(sel["quota_skipped"]) == 12
        assert sel["pending_count"] == 17

    def test_matrix_c_unlimited_selects_all(self):
        rows = [_row(w, f"B7.1.1.{w}.1") for w in range(1, 18)]
        sel = _select(rows, remaining=0, unlimited=True)
        assert sel["selected_count"] == 17
        assert sel["quota_skipped"] == []

    def test_matrix_d_4_pending_10_quota_selects_all_4(self):
        rows = [_row(w, f"B7.1.1.{w}.1") for w in range(1, 5)]
        sel = _select(rows, remaining=10)
        assert sel["selected_count"] == 4
        assert sel["quota_skipped"] == []

    def test_matrix_e_needs_review_never_selected(self):
        rows = [
            _row(1, "B7.1.1.1.1"),
            _row(2, "B7.1.1.2.1", needs_review=True),
            _row(3, "B7.1.1.3.1"),
        ]
        sel = _select(rows, remaining=5)
        assert sel["selected_count"] == 2
        assert "week2:0:B7.1.1.2.1" not in sel["selected_occurrence_ids"]
        assert sel["needs_review_count"] == 1
        assert sel["needs_review_items"][0]["week_number"] == 2

        # All-unsafe → nothing safe to run (the caller blocks for review).
        all_unsafe = [_row(1, "B7.1.1.1.1", needs_review=True)]
        assert _select(all_unsafe, remaining=5)["safe_pending_count"] == 0

    def test_matrix_h_repeated_indicator_is_two_occurrences_one_unit(self):
        rows = [
            _row(5, "B9.1.3.1.1", occ="week5:0:B9.1.3.1.1"),
            _row(6, "B9.1.3.1.1", occ="week6:0:B9.1.3.1.1"),
        ]
        sel = _select(rows, remaining=1)
        assert sel["selected_count"] == 2, "cross-week recurrence stays two lessons"
        assert sel["selected_indicator_codes"] == ["B9.1.3.1.1"], "one quota unit"
        assert sel["quota_skipped"] == []

    def test_matrix_i_special_period_rows_never_generate(self):
        rows = [
            _row(1, "B7.1.1.1.1"),
            _row(8, "", occ="week8:0:special", special=True),
        ]
        sel = _select(rows, remaining=5)
        assert sel["selected_count"] == 1
        assert sel["pending_count"] == 1, "special rows are not pending lessons"

    def test_generated_occurrences_are_pending_only(self):
        rows = [_row(w, f"B7.1.1.{w}.1") for w in range(1, 4)]
        sel = _select(rows, remaining=5, generated=["week1:0:B7.1.1.1.1"])
        assert sel["pending_count"] == 2
        assert sel["selected_count"] == 2
        assert "week1:0:B7.1.1.1.1" not in sel["selected_occurrence_ids"]

    def test_matrix_k_zero_quota_selects_nothing(self):
        rows = [_row(1, "B7.1.1.1.1")]
        sel = _select(rows, remaining=0)
        assert sel["selected_count"] == 0
        assert len(sel["quota_skipped"]) == 1

    def test_indicatorless_scheme_selects_everything_regardless_of_quota(self):
        rows = [
            {"source_occurrence_id": f"week{w}:0:row", "indicator_code": "",
             "needs_review": False, "is_special_period": False, "week_number": w}
            for w in range(1, 9)
        ]
        sel = _select(rows, remaining=0, indicatorless=True)
        assert sel["selected_count"] == 8


class TestBlockersAndWapef:
    def test_wapef_not_required_for_ordinary_templates(self):
        state = wapef_autopilot_state("tpl-ges-basic", {})
        assert state == {"required": False, "saved": True, "template_id": "tpl-ges-basic"}

    def test_matrix_f_wapef_with_saved_values_is_ready(self):
        drafts = {"3": {"wapef_deep_hope": "Learners see themselves as unique"}}
        state = wapef_autopilot_state("tpl-wapef-approved-plan", drafts)
        assert state["required"] and state["saved"]

    def test_matrix_g_wapef_without_saved_values_requires_input(self):
        state = wapef_autopilot_state("tpl-wapef-approved-plan", {"3": {"keywords": ["x"]}})
        assert state["required"] and not state["saved"]
        blockers = selection_blockers(
            detection_status="single", subject="Creative Arts", class_level="Basic 9",
            confirmed_class="Basic 9", is_known_class_level=lambda c: True,
            quota_selected_count=5, safe_pending_count=5, pending_count=5,
            needs_review_count=0, wapef=state, quota_remaining=5,
            quota_message_for_empty=lambda: "quota empty",
        )
        assert [b["code"] for b in blockers] == ["wapef_required"]
        assert "choose your WAPEF values once" in blockers[0]["message"]

    def test_only_genuine_interruptions_block(self):
        ok = dict(
            detection_status="single", subject="ICT", class_level="Basic 7",
            confirmed_class="Basic 7", is_known_class_level=lambda c: True,
            quota_selected_count=5, safe_pending_count=17, pending_count=17,
            needs_review_count=0, wapef={"required": False, "saved": True},
            quota_remaining=5, quota_message_for_empty=lambda: "quota empty",
        )
        assert selection_blockers(**ok) == []

    def test_subject_and_class_gaps_block_with_teacher_facing_copy(self):
        base = dict(
            detection_status="single", subject="Unknown", class_level="Unknown",
            confirmed_class="", is_known_class_level=lambda c: False,
            quota_selected_count=5, safe_pending_count=5, pending_count=5,
            needs_review_count=0, wapef={"required": False, "saved": True},
            quota_remaining=5, quota_message_for_empty=lambda: "quota empty",
        )
        codes = [b["code"] for b in selection_blockers(**base)]
        assert codes == ["subject_confirmation", "class_confirmation"]

        multi = dict(base, detection_status="multiple", subject="Science")
        assert selection_blockers(**multi)[0]["code"] == "subject_confirmation"

    def test_matrix_k_exhausted_quota_message(self):
        state = dict(
            detection_status="single", subject="ICT", class_level="Basic 7",
            confirmed_class="Basic 7", is_known_class_level=lambda c: True,
            quota_selected_count=0, safe_pending_count=17, pending_count=17,
            needs_review_count=0, wapef={"required": False, "saved": True},
            quota_remaining=0, quota_message_for_empty=lambda: "You've used all 5.",
        )
        blockers = selection_blockers(**state)
        assert [b["code"] for b in blockers] == ["quota_exhausted"]
        assert blockers[0]["message"].startswith("You've used all 5.")

    def test_nothing_pending_is_its_own_state(self):
        state = dict(
            detection_status="single", subject="ICT", class_level="Basic 7",
            confirmed_class="Basic 7", is_known_class_level=lambda c: True,
            quota_selected_count=0, safe_pending_count=0, pending_count=0,
            needs_review_count=0, wapef={"required": False, "saved": True},
            quota_remaining=5, quota_message_for_empty=lambda: "quota empty",
        )
        assert selection_blockers(**state)[0]["code"] == "nothing_pending"

    def test_matrix_l_default_generation_mode_is_deterministic_off(self):
        assert TermConfig(scheme_of_work_id="x").ai_mode.value == "OFF"


# ── API end-to-end (the endpoint the browser calls) ─────────────────────────

def _multi_scheme(db, owner_id, weeks, code_for, class_level="Basic 7"):
    scheme = SchemeDB(
        id=generate_id(), owner_id=owner_id, filename="Autopilot Scheme.docx",
        subject="ICT", class_level=class_level, term="First Term",
        academic_year="2026/2027", status="extracted", detection_status="single",
    )
    db.add(scheme)
    db.flush()
    for n in range(1, weeks + 1):
        code = code_for(n)
        db.add(WeekDB(
            id=generate_id(), scheme_id=scheme.id, week_number=n,
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 11),
            week_type="instruction", strand="Introduction to Computing",
            sub_strand="Components of Computers",
            content_standards=[f"B7.1.1.{n}"],
            indicators=[f"{code} Identify the parts of a computer"],
            resources=["Keyboard"],
        ))
    db.commit()
    return scheme


def _config(scheme_id, **over):
    data = dict(
        scheme_of_work_id=scheme_id,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=3, lesson_duration_minutes=60, class_size=30,
        teaching_days=[0, 2, 4], holidays=[], ai_mode="OFF",
        include_special_weeks=False, class_level="Basic 7", subject="ICT",
    )
    data.update(over)
    return TermConfig(**data)


def _app(db, user):
    from fastapi import FastAPI
    from src.auth import get_current_user, require_teacher_workflow
    from src.database import get_db
    from src.routers import generation as gen_router

    app = FastAPI()
    app.include_router(gen_router.router, prefix="/api/generation")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_teacher_workflow] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    return app


def _select_via(client, scheme, config):
    resp = client.post(
        f"/api/generation/{scheme.id}/autopilot-selection",
        json=config.model_dump(mode="json"),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _generate(client, scheme, config, **extra):
    body = config.model_dump(mode="json")
    body.update(extra)
    resp = client.post(f"/api/generation/{scheme.id}/generate", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _lessons(client, scheme):
    resp = client.get(f"/api/generation/schemes/{scheme.id}/lessons")
    assert resp.status_code == 200, resp.text
    return resp.json()["lesson_plans"]


def _jobs(client):
    resp = client.get("/api/generation/quota")
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestAutopilotApi:
    def test_matrix_a_all_detected_is_one_click_ready(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _multi_scheme(db, user.id, weeks=3, code_for=lambda n: f"B7.1.1.{n}.1")
        config = _config(scheme.id)

        with TestClient(_app(db, user)) as client:
            plan = _select_via(client, scheme, config)
            assert plan["ready"] is True
            assert plan["blockers"] == []
            assert plan["counts"] == {
                "pending_count": 3, "safe_pending_count": 3,
                "needs_review_count": 0, "selected_count": 3,
                "generated_count": 0, "quota_skipped_count": 0,
            }
            # Source order: earliest week first.
            assert [r["week_number"] for r in plan["selected_rows"]] == [1, 2, 3]
            assert plan["quota"]["remaining"] == 5
            assert plan["wapef"]["required"] is False
            # Deterministic default: the plan never implies AI.
            blob = str(plan).lower()
            assert "groq" not in blob and "gemini" not in blob

    def test_matrix_b_api_caps_selection_at_the_monthly_allowance(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _multi_scheme(db, user.id, weeks=7, code_for=lambda n: f"B7.2.{n}.1.1")
        config = _config(scheme.id)

        with TestClient(_app(db, user)) as client:
            plan = _select_via(client, scheme, config)
            assert plan["ready"] is True
            assert plan["counts"]["pending_count"] == 7
            assert plan["counts"]["selected_count"] == 5
            assert plan["counts"]["quota_skipped_count"] == 2
            assert len(plan["selected_indicator_codes"]) == 5
            # The capped batch is generation-ready through the REAL endpoint:
            # 5 codes fit the remaining 5 units, so no 403 and no job-less failure.
            _generate(
                client, scheme, config,
                selected_occurrence_ids=plan["selected_occurrence_ids"],
                selected_indicator_codes=plan["selected_indicator_codes"],
            )
            assert len(_lessons(client, scheme)) == 5

    def test_matrix_c_unlimited_account_generates_everything(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        db.add(EntitlementDB(user_id=user.id, edition="pro", generation_limit=0))
        db.commit()
        scheme = _multi_scheme(db, user.id, weeks=9, code_for=lambda n: f"B7.3.{n}.1.1")
        config = _config(scheme.id)

        with TestClient(_app(db, user)) as client:
            plan = _select_via(client, scheme, config)
            assert plan["ready"] is True
            assert plan["quota"]["unlimited"] is True
            assert plan["counts"]["selected_count"] == 9
            assert plan["counts"]["quota_skipped_count"] == 0

    def test_matrix_d_small_scheme_fits_inside_the_allowance(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _multi_scheme(db, user.id, weeks=4, code_for=lambda n: f"B7.4.{n}.1.1")
        config = _config(scheme.id)

        with TestClient(_app(db, user)) as client:
            plan = _select_via(client, scheme, config)
            assert plan["counts"]["selected_count"] == 4
            assert plan["counts"]["quota_skipped_count"] == 0
            assert plan["ready"] is True

    def test_matrix_j_partial_generation_leaves_the_rest_pending(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _multi_scheme(db, user.id, weeks=3, code_for=lambda n: f"B7.5.{n}.1.1")
        config = _config(scheme.id)

        with TestClient(_app(db, user)) as client:
            plan = _select_via(client, scheme, config)
            # First run: one lesson succeeds (the others "fail"/unstarted).
            first = plan["selected_occurrence_ids"][0]
            _generate(client, scheme, config,
                      selected_occurrence_ids=[first],
                      selected_indicator_codes=plan["selected_indicator_codes"][:1])
            # Resume: the generated one is gone from pending; the rest remain.
            again = _select_via(client, scheme, config)
            assert again["counts"]["generated_count"] == 1
            assert again["counts"]["pending_count"] == 2
            assert first not in again["selected_occurrence_ids"]
            assert again["ready"] is True

    def test_matrix_k_exhausted_quota_blocks_with_clear_message_and_no_job(self, db):
        from fastapi.testclient import TestClient
        from src.usage_quota import reserve_lesson_units

        user = make_user(db)
        scheme = _multi_scheme(db, user.id, weeks=3, code_for=lambda n: f"B7.6.{n}.1.1")
        config = _config(scheme.id)

        with TestClient(_app(db, user)) as client:
            reservation = reserve_lesson_units(
                db, user.id, scheme.id,
                ["B7.6.1.1.1", "B7.6.2.1.1", "B7.6.3.1.1",
                 "B7.6.9.1.1", "B7.6.8.1.1"],
                5,
            )
            assert reservation.allowed

            plan = _select_via(client, scheme, config)
            assert plan["ready"] is False
            assert [b["code"] for b in plan["blockers"]] == ["quota_exhausted"]
            assert "Free Tier lesson plans" in plan["blockers"][0]["message"]

            # A direct generate attempt also stops BEFORE any job is created.
            before = client.get(
                f"/api/generation/scheme/{scheme.id}/status"
            ).json()
            resp = client.post(
                f"/api/generation/{scheme.id}/generate",
                json=config.model_dump(mode="json"),
            )
            assert resp.status_code == 403
            after = client.get(f"/api/generation/scheme/{scheme.id}/status").json()
            assert before is None and after is None, "no job created on exhaustion"

    def test_matrix_f_saved_wapef_drafts_do_not_block(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _multi_scheme(db, user.id, weeks=2, code_for=lambda n: f"B7.7.{n}.1.1")
        scheme.lesson_review_drafts = {
            "1": {"wapef_deep_hope": "Every learner is created unique"}
        }
        db.commit()
        config = _config(scheme.id, template_id="tpl-wapef-approved-plan")

        with TestClient(_app(db, user)) as client:
            plan = _select_via(client, scheme, config)
            assert plan["ready"] is True
            assert plan["wapef"] == {
                "required": True, "saved": True,
                "template_id": "tpl-wapef-approved-plan",
            }

    def test_matrix_g_missing_wapef_is_the_only_interruption_then_resumes(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _multi_scheme(db, user.id, weeks=2, code_for=lambda n: f"B7.8.{n}.1.1")
        config = _config(scheme.id, template_id="tpl-wapef-approved-plan")

        with TestClient(_app(db, user)) as client:
            plan = _select_via(client, scheme, config)
            assert plan["ready"] is False
            assert [b["code"] for b in plan["blockers"]] == ["wapef_required"]

            # The teacher saves WAPEF once (the real PUT the review card uses).
            saved = client.put(
                f"/api/generation/{scheme.id}/lesson-review",
                json={"drafts": {"1": {
                    "wapef_deep_hope": "I am fearfully and wonderfully made",
                    "wapef_storyline": "Unique creation",
                }}},
            )
            assert saved.status_code == 200, saved.text

            plan2 = _select_via(client, scheme, config)
            assert plan2["ready"] is True
            assert plan2["blockers"] == []

    def test_unknown_subject_blocks_without_touching_jobs(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _multi_scheme(db, user.id, weeks=2, code_for=lambda n: f"B7.9.{n}.1.1")
        scheme.subject = "Unknown"
        db.commit()
        config = _config(scheme.id)

        with TestClient(_app(db, user)) as client:
            plan = _select_via(client, scheme, config)
            assert plan["ready"] is False
            assert [b["code"] for b in plan["blockers"]] == ["subject_confirmation"]

    def test_unstated_class_blocks_until_confirmed(self, db):
        from fastapi.testclient import TestClient

        user = make_user(db)
        scheme = _multi_scheme(db, user.id, weeks=2, code_for=lambda n: f"B7.10.{n}.1.1")
        scheme.class_level = "Unknown"
        db.commit()
        config = _config(scheme.id, class_level="Unknown")

        with TestClient(_app(db, user)) as client:
            plan = _select_via(client, scheme, config)
            assert [b["code"] for b in plan["blockers"]] == ["class_confirmation"]

            # The teacher's choice unblocks without any other configuration.
            confirmed = _select_via(client, scheme, _config(scheme.id))
            assert confirmed["ready"] is True
            db.refresh(scheme)
            assert scheme.class_level == "Basic 7"
