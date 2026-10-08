"""Priority 3.1 — §26/§27 UI source-contract tests for zero-decision Autopilot.

The frontend has no test runner, so the screen half of the Autopilot spec is
pinned at the source level here (the rules half lives in
test_autopilot_generation.py and the browser journey in
frontend/e2e/autopilot-acceptance.js). Every check maps to a spec clause:

  §2  upload → ONE explicit action → plans, config still available
  §17 genuine interruptions only (subject / class / WAPEF / nothing / quota)
  §18 results view: "N lesson plans ready" + week/topic/status/Open lesson
  §19 the advanced/manual week-centric flow is untouched
  §20 the browser never computes what fits this month (server plan only)
  §25 honest progress: ordered work list, no fake per-item completion
"""
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
UPLOAD = FRONTEND / "src" / "app" / "(app)" / "upload" / "page.tsx"
PAGE = FRONTEND / "src" / "app" / "(app)" / "generate" / "[id]" / "page.tsx"
API = FRONTEND / "src" / "lib" / "api.ts"
REVIEW = FRONTEND / "src" / "app" / "(app)" / "review" / "[id]" / "page.tsx"


def _upload() -> str:
    return UPLOAD.read_text(encoding="utf-8")


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def _api() -> str:
    return API.read_text(encoding="utf-8")


class TestUploadOneAction:
    def test_primary_button_is_the_generation_action(self):
        src = _upload()
        assert "data-autopilot-upload" in src
        assert "Generate my lesson plans" in src

    def test_click_records_intent_and_hands_to_generate(self):
        src = _upload()
        assert "schemeknit.autopilot_intent" in src
        # ONE click → straight to the Generate page (no config screen in
        # between); the intent is consumed there, exactly once.
        assert "router.push(`/generate/${result.scheme_id}`)" in src

    def test_review_and_dashboard_remain_secondary(self):
        src = _upload()
        assert "Review Curriculum" in src
        assert "Back to Dashboard" in src


class TestGenerateAutopilotCard:
    def test_card_and_every_action_surface_exists(self):
        src = _page()
        for attr in (
            "data-autopilot",
            "data-autopilot-counts",
            "data-autopilot-blocker",
            "data-autopilot-review",
            "data-autopilot-action",
            "data-autopilot-manual",
            "data-autopilot-settings",
        ):
            assert attr in src, f"missing {attr}"

    def test_one_click_handler_posts_the_server_plan(self):
        src = _page()
        assert "handleAutopilot" in src
        assert "api.autopilotSelection" in src
        # The click generates exactly the server's plan — no local rebuild.
        assert "plan.selected_indicator_codes" in src
        assert "plan.selected_occurrence_ids" in src
        assert "plan.selected_rows" in src

    def test_plain_visits_never_auto_generate(self):
        src = _page()
        # Auto-fire only after the upload page's intent flag; a plain visit
        # merely loads the plan (§17 quota never spent without a click).
        assert "autopilotIntent.current = true" in src
        assert "schemeknit.autopilot_intent" in src
        assert "autopilotIntent.current = false" in src
        assert "autopilotFired.current = true" in src

    def test_blocker_codes_render_with_smallest_interrupt(self):
        src = _page()
        for code in (
            "wapef_required",
            "class_confirmation",
            "subject_confirmation",
            "extraction_failed",
            "needs_review",
        ):
            assert f"'{code}'" in src, f"missing blocker {code}"
        # The WAPEF interrupt scrolls to the WAPEF inputs only.
        assert "focusWapef" in src

    def test_capped_label_shows_the_exact_count(self):
        src = _page()
        assert "quota_skipped_count > 0" in src
        assert "`Generate ${autopilot.counts?.selected_count ?? 0} lesson plans`" in src


class TestHonestProgressAndResults:
    def test_progress_is_an_ordered_work_list_not_a_fake_percent(self):
        src = _page()
        assert "data-autopilot-progress" in src
        assert "data-progress-row" in src
        assert "progressRows.length" in src
        # The list is a plain ordered enumeration of what the click is
        # generating — no polling loop, no per-item completion percentages,
        # no claimed progress the synchronous POST cannot report (§25).
        assert "setInterval" not in src
        assert "of {progressRows.length} · Week" in src

    def test_results_card_lists_week_topic_status_and_open_lesson(self):
        src = _page()
        assert "data-autopilot-results" in src
        assert "lesson plans ready" in src
        assert "Open lesson" in src
        assert "Generated" in src
        # Single lesson opens the workspace directly (§18).
        assert "progress.length > 1" in src


class TestServerAuthoritativeQuota:
    def test_api_exposes_the_selection_endpoint_and_preferences(self):
        api = _api()
        assert "autopilotSelection" in api
        assert "/autopilot-selection" in api
        assert "getPreferences" in api
        assert "/api/settings/preferences" in api

    def test_the_browser_never_counts_the_allowance_itself(self):
        src = _page()
        # The card renders the server plan's counts verbatim (§20).
        assert "autopilot.counts" in src
        assert "api.autopilotSelection" in src
        # The ONE-click handler never rebuilds a selection locally — it
        # generates exactly what the plan returned (unlike the P3 manual
        # rail's fullSelection, which stays untouched).
        start = src.index("const handleAutopilot")
        end = src.index("const scrollTo", start)
        body = src[start:end]
        assert "fullSelection" not in body
        assert "plan.selected_indicator_codes" in body
        assert "plan.selected_occurrence_ids" in body


class TestManualFlowUntouched:
    def test_config_weeks_and_review_surfaces_stay_visible(self):
        src = _page()
        for attr in (
            "data-generate-config",
            "data-allocation-preview",
            "data-lesson-review",
            "data-generate-summary",
        ):
            assert attr in src, f"missing {attr}"
        # Priority-3 one-click-all contract keeps its exact words.
        assert "Generating your lesson plans" in src
        assert "quotaLine" in src

    def test_review_page_label_is_unchanged(self):
        assert "Approve & Configure" in REVIEW.read_text(encoding="utf-8")

    def test_term_dates_are_seeded_from_the_scheme_not_hardcoded(self):
        src = _page()
        assert "weekStarts[0] || prev.term_start_date" in src
        assert "weekEnds[weekEnds.length - 1] || prev.term_end_date" in src
        assert "default_lesson_duration" in src
