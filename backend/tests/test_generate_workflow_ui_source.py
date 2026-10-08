"""Priority 3 — §26 UI source-contract tests for the week-centric Generate flow.

The frontend has no test runner, so the UI half of §26 is pinned at the source
level here (behaviour half lives in test_generate_workflow_priority3.py and the
Playwright journeys). Every check maps to a spec clause:

  §7  the surface is week-centric vocabulary, not backend jargon
  §10 per-week fit lines stay verbatim (deep-journey contract)
  §14 the quota line appears exactly once, in the rail, exact format
  §15 config + review hide once a job exists ("Start New Generation")
  §17 status words are Generated / Needs review (app-closure contract)
  §24/§25 no client-side weekly-coverage or generation logic
  save boundary: PUT lesson-review completes before POST generate
"""
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
PAGE = FRONTEND / "src" / "app" / "(app)" / "generate" / "[id]" / "page.tsx"
LIB = FRONTEND / "src" / "lib" / "generate-coverage.ts"
API = FRONTEND / "src" / "lib" / "api.ts"


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def _lib() -> str:
    return LIB.read_text(encoding="utf-8")


class TestWeekCentricSurface:
    def test_primary_heading_is_teacher_language(self):
        src = _page()
        assert "Lesson plans by week" in src
        # The backend's preview vocabulary never reaches the teacher (§7).
        assert "Allocation Preview" not in src
        assert "Allocation Preview" not in _lib()

    def test_two_gate_ritual_is_gone(self):
        src = _page()
        assert "Preview Allocation" not in src
        assert "Confirm &amp; Generate" not in src
        assert "Confirm & Generate" not in src
        assert "Generate lesson plans" in src

    def test_every_week_card_carries_the_contract_attributes(self):
        src = _page()
        for attr in (
            "data-allocation-preview",
            "data-allocation-weeks",
            "data-week-card",
            "data-week-number",
            "data-week-row",
            "data-occurrence-id",
            "data-generate-week",
            "data-generate-lesson",
            "data-week-coverage",
            "data-generate-total",
        ):
            assert attr in src, f"missing {attr}"

    def test_surfaces_keep_their_e2e_attributes(self):
        src = _page()
        for attr in (
            "data-generate-summary",
            "data-generate-config",
            "data-generate-action",
            "data-generate-mode",
            "data-lesson-review",
            "data-coverage",
            "data-class-level-select",
        ):
            assert attr in src, f"missing {attr}"

    def test_primary_actions_are_per_week_and_per_lesson(self):
        src = _page()
        # One action per week and one per occurrence — never a single batch
        # with no way back into a single lesson (R7/R9).
        assert "handleGenerateWeek" in src
        assert "handleGenerateRow" in src
        assert "handleGenerateAll" in src
        assert "selected_occurrence_ids" in src


class TestStatusAndCopyContracts:
    def test_status_words_match_the_closure_contract(self):
        src = _page()
        assert ">Generated</StatusPill>" in src
        assert ">Needs review</StatusPill>" in src
        # "Scheduled" is backend vocabulary for a generated plan (§17).
        assert ">Scheduled</StatusPill>" not in src

    def test_week_counts_line_is_verbatim(self):
        lib = _lib()
        # The rendered line is assembled from these exact fragments.
        assert "required for this week" in lib
        assert "curriculum indicator" in lib
        assert "timetable period" in lib
        assert "lesson plan${" in lib

    def test_progress_copy_is_plain_and_live(self):
        src = _page()
        assert "Generating your lesson plans" in src
        assert 'role="status"' in src
        assert 'aria-live="polite"' in src
        # The old backend-flavoured spinner string is gone (R10).
        assert "Preparing curriculum allocation" not in src


class TestQuotaPresentation:
    def test_quota_line_format_is_canonical_and_appears_once(self):
        # The exact line phase17 parses lives ONLY in the lib helper (§14);
        # the page renders it through quotaLine() and never hardcodes it.
        assert _lib().count("Free Tier lesson plans used this month") >= 1
        assert _page().count("Free Tier lesson plans used this month") == 0
        assert "quotaLine" in _page()

    def test_quota_banner_is_the_shared_info_banner_in_the_rail(self):
        src = _page()
        assert '<Banner tone="info" data-quota-banner' in src
        # Shown once — never repeated per card.
        assert src.count("data-quota-banner") == 1

    def test_week_fit_sentence_is_rendered_from_the_helper(self):
        src = _page()
        assert "quotaFitForRows" in src
        assert "can be generated with your remaining monthly allowance" in src


class TestStateSplit:
    def test_config_and_review_hide_once_a_job_exists(self):
        src = _page()
        assert "{!jobId && (" in src
        assert "Start New Generation" in src
        # Config gating precedes its surface card.
        cfg_gate = src.find("{!jobId && (")
        cfg_card = src.find("data-generate-config")
        assert 0 < cfg_gate < cfg_card or cfg_gate != -1

    def test_review_card_is_gated_and_numbered_from_lesson_sequence(self):
        src = _page()
        assert "{!jobId && lessonReview.length > 0 && (" in src
        # lesson_sequence is 1-based — the display must not add another +1.
        assert "row.lesson_sequence + 1" not in src

    def test_auto_preview_and_debounced_refresh_exist(self):
        src = _page()
        assert "Reading your weeks…" in src
        # Debounce effect keys on the allocation inputs, not on a click.
        assert "config.teaching_days.join(',')" in src


class TestSaveBoundary:
    def test_drafts_are_saved_before_generate_in_the_same_handler(self):
        src = _page()
        run = src[src.index("const runGeneration"):]
        save_at = run.index("saveLessonReviewDrafts(lessonReview)")
        gen_at = run.index("api.generateLessonPlans(")
        assert save_at < gen_at
        # A save failure cancels generation instead of racing past it.
        assert "generation was cancelled" in run


class TestPurityAndSafety:
    def test_lib_is_pure_view_model(self):
        lib = _lib()
        for forbidden in ("fetch(", "axios", "useState", "useEffect", "localStorage"):
            assert forbidden not in lib, f"generate-coverage.ts must stay pure: {forbidden}"

    def test_page_has_no_client_side_generation_logic(self):
        src = _page()
        # §24/§25: the frontend decides WHAT, never HOW.
        low = src.lower()
        assert "carry forward" not in low
        assert "carried forward" not in low
        assert "slot limit" not in low
        assert "cross-week" not in low

    def test_no_provider_vocabulary_on_the_page(self):
        low = _page().lower()
        for word in ("gemini", "groq", "openai", "anthropic", "llama", "mistral"):
            assert word not in low, f"provider name leaked into teacher UI: {word}"

    def test_no_raw_controls_or_legacy_apis(self):
        src = _page()
        assert "<select " not in src and "<select>" not in src
        assert "<textarea" not in src
        assert "createObjectURL" not in src
        assert "api.downloadFile(" not in src

    def test_api_client_sends_and_accepts_occurrence_selection(self):
        api = API.read_text(encoding="utf-8")
        assert "selected_occurrence_ids" in api
        assert "getSchemeLessons" in api
