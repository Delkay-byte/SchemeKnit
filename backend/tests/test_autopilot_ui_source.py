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

    def test_confirm_path_also_hands_to_autopilot(self):
        """Backlog item 5: after the teacher resolves the one genuine
        ambiguity (subject/class), the confirm path records the same intent
        and hands off to Autopilot — no dead-end at /review."""
        src = _upload()
        # The confirm handler must set the intent flag…
        assert "schemeknit.autopilot_intent" in src
        # …and route to /generate (not /review) after a successful confirm.
        # handleConfirmSubject is the only place confirmSubjectSection is
        # called; its success branch must push to /generate.
        i = src.index("handleConfirmSubject")
        handler = src[i:i + 1400]
        assert "confirmSubjectSection" in handler
        assert "schemeknit.autopilot_intent" in handler
        assert "router.push(`/generate/" in handler
        assert "router.push(`/review/" not in handler

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
        assert "readyRows.length > 1" in src
        # Only accepted occurrences may be listed as ready — a gate-rejected
        # lesson stays pending and is reported separately.
        assert "response.generated_occurrence_ids" in src
        assert "response.rejected_occurrence_ids" in src
        assert "data-batch-notice" in src


class TestAutopilotOutcomeSummary:
    def test_outcome_names_every_real_batch_field(self):
        """The result summary must use the POST /generate response, not counts
        inferred from the rows the browser happened to send."""
        src = _page()
        assert "data-autopilot-outcome" in src
        assert "response.generated_occurrence_ids" in src
        assert "response.already_generated_occurrence_ids" in src
        assert "response.rejected_occurrence_ids" in src
        assert "response.pending_occurrence_ids" in src

    def test_quota_wait_line_comes_from_the_server_plan(self):
        """Only the API plan may claim work 'waits for next month'."""
        src = _page()
        # The fields are populated from the server plan…
        start = src.index("const runGeneration")
        end = src.index("const handleGenerateAll", start)
        body = src[start:end]
        assert "plan.counts?.quota_skipped_count" in body
        assert "plan.counts?.needs_review_count" in body
        # …and the rendered line only repeats those outcome fields.
        start = src.index("data-autopilot-outcome")
        end = src.index("data-autopilot-results", start)
        render = src[start:end]
        assert "autopilotOutcome.quotaSkipped" in render
        assert "autopilotOutcome.needsReview" in render
        assert "wait for next month" in render


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


class TestGenerationRecoverySurface:
    def test_failed_interrupted_job_is_reported_with_a_retry(self):
        """A failed/restart-orphaned job must not vanish on reload.

        The status endpoint now reclaims stale jobs as failed; the page must
        say so and keep the one-click retry available.
        """
        src = _page()
        assert "data-generation-recovery" in src
        assert "statusData?.status === 'failed'" in src
        assert "statusData?.can_resume" in src, (
            "the banner must follow the server's terminal-state verdict, not "
            "merely the presence of planned-but-unwritten occurrences (a "
            "still-processing job also has those)")
        assert "error_message" in src
        assert "api.resumeGeneration" in src
        start = src.index("data-generation-recovery")
        body = src[start:src.index("data-batch-notice", start)]
        # A planned-but-unfinished job offers a true resume; a legacy/unknown
        # job falls back to the re-planning retry.
        assert "runResume" in body
        assert "Resume pending lessons" in body
        assert "data-generation-resume" in body
        assert "handleAutopilot" in body
        assert "data-generation-retry" in body
        assert "Try again" in body

    def test_api_has_a_dedicated_resume_call(self):
        src = _api()
        assert "async resumeGeneration" in src
        assert "/generate/resume" in src
        assert "job_id: jobId" in src


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

    def test_committed_run_finalization_warning_is_surfaced(self):
        """A committed run with a finalization warning must not look clean.

        The API returns `warning` on the POST response and persists
        `finalization_warning` for reloads. The page must consume both and
        render a dedicated banner, not merely report an unqualified success.
        """
        src = _page()
        assert "finalization_warning" in src
        assert "response.warning" in src
        assert "data-finalization-warning" in src
        assert "default_lesson_duration" in src
