"""
Template catalog + AI provider + per-lesson metadata regression tests
(Parts A/B/C/D/E/F–V/W of the remediation).
"""
import json
from datetime import date
from unittest.mock import patch

import pytest

from src.models import (
    AIMode, ClassLevel, NACCA_COMPETENCY_LABELS, ReferenceEntry, Subject,
    TermConfig, Week, WeekType,
)
from src.engines.template_engine import (
    DEFAULT_TEMPLATES, RETIRED_TEMPLATE_IDS, get_template_by_id,
    get_templates_for_level, get_default_template_for_class_level,
)
from src.engines.template_provenance import provenance_for_template
from src.engines.official_ges_levels import (
    JHS_SPEC, PRIMARY_SPEC, KG_SPEC, SHS_SPEC, spec_for_template_id,
)
from src.engines.wapef_template import TEMPLATE_ID as WAPEF_ID
from src.engines.wapef_basic13_template import TEMPLATE_ID as WAPEF_B13_ID
from src.engines.allocation_engine import AllocationEngine
from src.engines.calendar_engine import CalendarEngine
from src.curriculum.lesson_builder import build_lesson


# ── Part A/B/C — template catalog ────────────────────────────────────────────

class TestTemplateCatalog:
    def test_all_active_templates_present(self):
        """The registry enumerates the REAL active set — 11 active templates,
        not a hard-coded two."""
        assert len(DEFAULT_TEMPLATES) == 11
        ids = {t.id for t in DEFAULT_TEMPLATES}
        assert ids == {
            JHS_SPEC.template_id, KG_SPEC.template_id,
            PRIMARY_SPEC.template_id, SHS_SPEC.template_id,
            "tpl-jhs-ges", "tpl-jhs-professional", "tpl-primary-standard",
            "tpl-ec-activity", "tpl-shs-ges",
            WAPEF_ID, WAPEF_B13_ID,
        }

    def test_retired_headteacher_not_selectable(self):
        assert "tpl-approved-org-headteacher" in RETIRED_TEMPLATE_IDS
        assert all(t.id != "tpl-approved-org-headteacher"
                   for t in DEFAULT_TEMPLATES)
        from src.models import EducationalLevel
        for level in EducationalLevel:
            ts = get_templates_for_level(level)
            assert all(t.id != "tpl-approved-org-headteacher" for t in ts)

    def test_retired_headteacher_still_routable_for_history(self):
        """Historical lessons/exports naming the retired id still resolve to
        the verified JHS renderer (referential integrity, PART C)."""
        tpl = get_template_by_id("tpl-approved-org-headteacher")
        assert tpl is not None
        assert spec_for_template_id("tpl-approved-org-headteacher") is JHS_SPEC
        prov = provenance_for_template("tpl-approved-org-headteacher")
        assert prov.verified and prov.official

    def test_ges_display_names_contain_ges(self):
        for spec in (JHS_SPEC, PRIMARY_SPEC, KG_SPEC, SHS_SPEC):
            tpl = get_template_by_id(spec.template_id)
            assert "GES" in tpl.name, spec.template_id

    def test_wapef_display_names_contain_wapef(self):
        for tid in (WAPEF_ID, WAPEF_B13_ID):
            tpl = get_template_by_id(tid)
            assert "WAPEF" in tpl.name, tid
        assert "1–3" in get_template_by_id(WAPEF_B13_ID).name or \
            "1-3" in get_template_by_id(WAPEF_B13_ID).name

    def test_no_headteacher_wording_anywhere_selectable(self):
        for t in DEFAULT_TEMPLATES:
            assert "Headteacher" not in t.name
            assert "headteacher" not in t.description.lower() or "retired" in t.description.lower()

    def test_class_routing_unchanged(self):
        """Part Z: Basic 1-3 default = GES lower primary; JHS = GES JHS;
        WAPEF templates remain available, never forced."""
        assert get_default_template_for_class_level(
            ClassLevel.BASIC_1).id == PRIMARY_SPEC.template_id
        assert get_default_template_for_class_level(
            ClassLevel.BASIC_8).id == JHS_SPEC.template_id
        ids_jhs = {t.id for t in DEFAULT_TEMPLATES}
        assert WAPEF_ID in ids_jhs and WAPEF_B13_ID in ids_jhs


# ── Part E — AI provider status correctness ──────────────────────────────────

class TestProviderResolution:
    def test_named_mode_resolves_to_itself(self):
        from src.engines.ai_provider import resolve_provider_mode
        with patch.dict("os.environ", {"GEMINI_API_KEY": "x", "AI_MODE": ""}):
            assert resolve_provider_mode("gemini") == "gemini"

    def test_named_gemini_never_reports_opencode_zen(self):
        """PART E: when the teacher pinned Gemini, the resolved provider key
        must be gemini — regardless of any other configured key or reachability
        of a different provider."""
        from src.engines.ai_provider import resolve_provider_mode, get_provider
        env = {"GEMINI_API_KEY": "x", "OPENCODE_ZEN_API_KEY": "y", "AI_MODE": ""}
        with patch.dict("os.environ", env):
            resolved = resolve_provider_mode("gemini")
            assert resolved == "gemini"
            provider = get_provider(resolved)
            assert provider.get_name() == "gemini"

    def test_basic_auto_select_prefers_configured_gemini(self):
        """Auto-selection must try key-holding providers in the documented
        order; a reachable Gemini is chosen over opencode-zen."""
        from src.engines.ai_provider import resolve_provider_mode
        env = {"GEMINI_API_KEY": "x", "OPENCODE_ZEN_API_KEY": "y", "AI_MODE": ""}
        with patch.dict("os.environ", env), \
                patch("src.engines.ai_provider.GeminiProvider.is_available",
                      return_value=True):
            assert resolve_provider_mode("BASIC") == "gemini"

    def test_opencode_zen_displayed_when_genuinely_resolved(self):
        """AA-9: opencode-zen remains the displayed provider when it is
        genuinely the resolved one (Gemini unavailable, Zen configured)."""
        from src.engines.ai_provider import resolve_provider_mode, get_provider
        env = {"OPENCODE_ZEN_API_KEY": "y", "GEMINI_API_KEY": "", "AI_MODE": ""}
        with patch.dict("os.environ", env), \
                patch("src.engines.ai_provider.GeminiProvider.is_available",
                      return_value=False):
            resolved = resolve_provider_mode("BASIC")
            assert resolved == "opencode-zen"
            assert get_provider(resolved).get_name() == "opencode-zen"


# ── Parts F–V — per-lesson metadata defaults ─────────────────────────────────

SCI_TLRS_W1 = ["Science textbook", "Chart of plants"]


def _cfg(**kw):
    return TermConfig(
        scheme_of_work_id="s", academic_year="2026/2027", term="First Term",
        class_level=ClassLevel.BASIC_8, subject=Subject.SCIENCE,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=3, lesson_duration_minutes=60,
        teaching_days=[0, 1, 2], holidays=[],
        keywords=list(kw.pop("keywords", []) or []),
        teaching_learning_resources=list(kw.pop("tlrs", []) or []),
        core_competencies=list(kw.pop("comps", []) or []),
        references=list(kw.pop("refs", []) or []),
        **kw,
    )


def _alloc(text, week=1, strand="Diversity", sub="Classification"):
    from src.models import AllocatedIndicator
    return AllocatedIndicator(
        indicator_code="B8.1.1.1", indicator_description=text,
        content_standard_code="B8.1.1.1",
        content_standard_description="B8.1.1.1 Learners classify organisms",
        strand=strand, sub_strand=sub, week_number=week,
        source_resources=list(SCI_TLRS_W1), lesson_date=date(2026, 9, 7),
        period_index=1, allocated=True, teaching_week=week,
    )


class TestPerLessonDefaults:
    def test_keywords_derive_from_indicator_not_batch(self):
        """PART G: keywords are lesson-specific, derived from the exact
        indicator first — two lessons do not share one generic list."""
        lp1 = build_lesson(
            _alloc("B8.1.1.1 Classify living organisms using keys"),
            _cfg(), "s")
        lp2 = build_lesson(
            _alloc("B8.1.1.1 Observe micro-organisms under a microscope"),
            _cfg(), "s")
        assert lp1.keywords and lp2.keywords
        # Each list leads with terms from its OWN indicator text.
        assert any("classify" in k.lower() or "organisms" in k.lower()
                   for k in lp1.keywords)
        assert any("micro" in k.lower() for k in lp2.keywords)
        # Empty config seed does not leave the lesson keyword-less.
        assert lp1.keywords != lp2.keywords

    def test_competencies_are_targeted_not_all(self):
        """PART H: never the whole taxonomy for every lesson."""
        lp = build_lesson(_alloc("B8.1.1.1 Classify living organisms"), _cfg(), "s")
        assert lp.core_competencies
        assert len(lp.core_competencies) < len(NACCA_COMPETENCY_LABELS)
        assert all(c in NACCA_COMPETENCY_LABELS for c in lp.core_competencies)

    def test_other_tlrs_default_empty(self):
        """PART I: Other TLRs start empty; the batch seed is never copied in."""
        lp = build_lesson(
            _alloc("B8.1.1.1 Classify living organisms"),
            _cfg(tlrs=["Teacher's handmade poster"]), "s")
        assert lp.other_tlrs == []
        assert lp.source_tlrs == SCI_TLRS_W1

    def test_source_tlrs_scoped_to_lesson(self):
        """PART J: source TLRs come from THIS lesson's allocation only."""
        from src.models import AllocatedIndicator
        other_week = AllocatedIndicator(
            indicator_code="B8.1.1.2", indicator_description="Observe cells",
            content_standard_code="B8.1.1.2",
            content_standard_description="std", strand="S", sub_strand="SS",
            week_number=2, source_resources=["Week-2 specific slide"],
            lesson_date=date(2026, 9, 14), period_index=1, allocated=True,
            teaching_week=2,
        )
        lp = build_lesson(other_week, _cfg(), "s")
        assert lp.source_tlrs == ["Week-2 specific slide"]

    def test_references_default_empty(self):
        """PART L/M: no invented curriculum/handbook references."""
        lp = build_lesson(_alloc("B8.1.1.1 Classify living organisms"), _cfg(), "s")
        assert lp.structured_references == []
        assert lp.references == []

    def test_period_empty_when_teacher_did_not_enter_one(self):
        """PART K/N: an empty field stays genuinely empty — no placeholder."""
        from src.engines.allocation_engine import AllocationEngine
        weeks = [Week(
            week_number=1, start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11), week_type=WeekType.INSTRUCTION,
            strand="Diversity", sub_strand="Classification",
            content_standards=["B8.1.1.1 std"],
            indicators=["B8.1.1.1 Classify living organisms"],
            resources=list(SCI_TLRS_W1), scheme_of_work_id="s",
        )]
        config = _cfg()
        config.period = ""
        cal = CalendarEngine().build_calendar(config, weeks, [])
        coverage = AllocationEngine().allocate(weeks, cal, config)
        plans = AllocationEngine().generate_lesson_plans(coverage, config, "s")
        assert plans[0].period == ""

    def test_period_preserved_when_teacher_enters_one(self):
        from src.engines.allocation_engine import AllocationEngine
        weeks = [Week(
            week_number=1, start_date=date(2026, 9, 7),
            end_date=date(2026, 9, 11), week_type=WeekType.INSTRUCTION,
            strand="Diversity", sub_strand="Classification",
            content_standards=["B8.1.1.1 std"],
            indicators=["B8.1.1.1 Classify living organisms"],
            resources=list(SCI_TLRS_W1), scheme_of_work_id="s",
        )]
        config = _cfg()
        config.period = "1st & 2nd"
        cal = CalendarEngine().build_calendar(config, weeks, [])
        coverage = AllocationEngine().allocate(weeks, cal, config)
        plans = AllocationEngine().generate_lesson_plans(coverage, config, "s")
        assert plans[0].period == "1st & 2nd"

    def test_empty_fields_render_empty(self):
        """PART N: no '-', '—', 'N/A', 'unknown', 'none' placeholders in any
        generated lesson string field."""
        lp = build_lesson(_alloc("B8.1.1.1 Classify living organisms"), _cfg(), "s")
        placeholders = {"-", "—", "–", "N/A", "n/a", "unknown", "none", "None",
                        "[]", '[""]'}
        for value in (lp.period, lp.lesson_topic or ""):
            assert value not in placeholders


class TestLessonIsolation:
    """PART V/AA-34..37: changing one lesson must never affect another."""

    def _apply(self):
        from src.routers.generation import _apply_lesson_review_draft
        return _apply_lesson_review_draft

    def test_keyword_edit_isolated(self):
        apply_drafts = self._apply()
        lp1 = build_lesson(_alloc("B8.1.1.1 Classify living organisms"), _cfg(), "s")
        lp2 = build_lesson(_alloc("B8.1.1.1 Observe micro-organisms"), _cfg(), "s")
        lp1.lesson_sequence, lp2.lesson_sequence = 0, 1
        before = list(lp2.keywords)
        apply_drafts(lp1, {"0": {"keywords": ["teacher-chosen-word"]}})
        assert "teacher-chosen-word" in lp1.keywords
        assert lp2.keywords == before
        assert "teacher-chosen-word" not in lp2.keywords

    def test_competency_edit_isolated(self):
        apply_drafts = self._apply()
        lp1 = build_lesson(_alloc("B8.1.1.1 Classify living organisms"), _cfg(), "s")
        lp2 = build_lesson(_alloc("B8.1.1.1 Observe micro-organisms"), _cfg(), "s")
        lp1.lesson_sequence, lp2.lesson_sequence = 0, 1
        before = list(lp2.core_competencies)
        apply_drafts(lp1, {"0": {"core_competencies": [NACCA_COMPETENCY_LABELS[5]]}})
        assert lp1.core_competencies == [NACCA_COMPETENCY_LABELS[5]]
        assert lp2.core_competencies == before

    def test_reference_edit_isolated(self):
        apply_drafts = self._apply()
        lp1 = build_lesson(_alloc("B8.1.1.1 Classify living organisms"), _cfg(), "s")
        lp2 = build_lesson(_alloc("B8.1.1.1 Observe micro-organisms"), _cfg(), "s")
        lp1.lesson_sequence, lp2.lesson_sequence = 0, 1
        apply_drafts(lp1, {"0": {"structured_references": [
            {"type": "Textbook", "title": "Science for Basic 8", "page": "12"},
        ]}})
        assert len(lp1.structured_references) == 1
        assert lp1.structured_references[0].page == "12"
        assert lp2.structured_references == []

    def test_other_tlr_edit_isolated(self):
        apply_drafts = self._apply()
        lp1 = build_lesson(_alloc("B8.1.1.1 Classify living organisms"), _cfg(), "s")
        lp2 = build_lesson(_alloc("B8.1.1.1 Observe micro-organisms"), _cfg(), "s")
        lp1.lesson_sequence, lp2.lesson_sequence = 0, 1
        apply_drafts(lp1, {"0": {"other_tlrs": ["Handmade poster"]}})
        assert lp1.other_tlrs == ["Handmade poster"]
        assert lp2.other_tlrs == []

    def test_empty_references_not_persisted(self):
        """PART L: empty slots are stripped on save — only non-empty
        references reach the stored lesson."""
        apply_drafts = self._apply()
        lp = build_lesson(_alloc("B8.1.1.1 Classify living organisms"), _cfg(), "s")
        lp.lesson_sequence = 0
        apply_drafts(lp, {"0": {"structured_references": [
            {"type": "Other", "title": "", "page": ""},
            {"type": "Textbook", "title": "Real Title", "page": "3"},
            {"type": "Other", "title": "  ", "page": ""},
        ]}})
        assert len(lp.structured_references) == 1
        assert lp.structured_references[0].title == "Real Title"
        assert lp.references == ["Real Title"]


# ── Part W — regeneration handling ───────────────────────────────────────────

class TestRegenerationSectionMapping:
    def test_valid_structured_response_maps_to_lesson_section(self):
        """AA-30: a valid structured Gemini/Groq response (starter/plenary
        keys) is NOT rejected as 'too short' for introduction/conclusion."""
        from src.routers.ai_regeneration import _extract_section_text
        gemini_style = {
            "learning_objectives": ["Learners can classify organisms"],
            "starter": {"activity": "Quick oral quiz on prior knowledge of "
                                    "living and non-living things."},
            "main_learning": {"phase1": {"name": "MAIN", "activity": "x"}},
            "assessment": {"activity": "Written exercise"},
            "plenary": "Learners summarise the classification key.",
        }
        intro = _extract_section_text(gemini_style, "introduction")
        concl = _extract_section_text(gemini_style, "conclusion")
        assert "oral quiz" in intro
        assert "classification key" in concl

    def test_flat_legacy_response_still_maps(self):
        from src.routers.ai_regeneration import _extract_section_text
        legacy = {"introduction": "A very direct introduction paragraph."}
        assert "introduction paragraph" in _extract_section_text(legacy, "introduction")

    def test_section_to_provider_keys_cover_every_section(self):
        from src.routers.ai_regeneration import (
            SECTION_TO_PROVIDER_KEYS, REGENERATABLE_SECTIONS,
        )
        assert set(SECTION_TO_PROVIDER_KEYS) == set(REGENERATABLE_SECTIONS)
        for keys in SECTION_TO_PROVIDER_KEYS.values():
            assert keys, "every section needs at least one provider key"
