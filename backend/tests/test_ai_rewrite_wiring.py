"""
AI Section Rewrite Wiring (the optional AI path)
=================================================

AI is OFF by default and only ever runs per-section when the teacher clicks
one of the two affordances ("Suggest another version" / "Make this more
practical"). These tests pin the contract:

* the prompt carries the ORIGINAL section, the indicator, the objective, the
  curriculum evidence, the subject, the resources and the approach — so the
  rewrite stays inside the curriculum lane;
* the prompt demands the same indicator code, objective meaning, subject,
  class, duration, resources and WAPEF selections be preserved;
* ``class_assignment`` / ``home_assignment`` are regeneratable sections;
* a provider that implements ``generate_structured`` receives the prompt
  verbatim (a rewrite, not a whole-lesson regeneration);
* provider failure preserves the deterministic content (502/503, teacher-safe).
"""

import sys
sys.path.insert(0, '.')

import pytest
from unittest.mock import patch
from fastapi import HTTPException
from pydantic import ValidationError

from src.routers import ai_regeneration as air
from src.routers.ai_regeneration import (
    REGENERATABLE_SECTIONS, REWRITE_MODES, DEFAULT_REWRITE_MODE,
    _build_section_prompt, _section_generation,
)
from src.engines.ai_provider import AIProvider


# ── Section catalog ──────────────────────────────────────────────────────────

def test_class_and_home_assignments_are_regeneratable():
    assert "class_assignment" in REGENERATABLE_SECTIONS
    assert "home_assignment" in REGENERATABLE_SECTIONS


def test_exactly_two_teacher_facing_rewrite_modes():
    """The UI offers two affordances — never an internal pattern name."""
    assert set(REWRITE_MODES) == {"suggest_another_version", "make_more_practical"}
    assert DEFAULT_REWRITE_MODE == "suggest_another_version"


def test_request_accepts_the_rewrite_mode():
    req = air.SectionRegenerateRequest(
        lesson_plan_id="x", section="assessment", rewrite_mode="make_more_practical")
    assert req.rewrite_mode == "make_more_practical"
    # and defaults to the safe affordance
    req2 = air.SectionRegenerateRequest(lesson_plan_id="x", section="assessment")
    assert req2.rewrite_mode == DEFAULT_REWRITE_MODE


# ── Prompt contract ──────────────────────────────────────────────────────────

class _LP:
    """A stand-in LessonPlanDB row for prompt construction."""
    def __init__(self, **over):
        base = dict(
            subject="Mathematics", class_level="Basic 7",
            strand="Number", sub_strand="Number and Numeration",
            content_standard="B7.1.1.1", content_standard_code="B7.1.1.1",
            indicators=["B7.1.1.1.1 Add whole numbers"],
            indicator_codes=["B7.1.1.1.1"],
            learning_objectives=[{"description": "Learners can add whole numbers."}],
            teaching_learning_resources=["counters", "place-value chart"],
            source_tlrs=["number cards"], other_tlrs=[],
            main_activities=[{"description": "Teacher works through one example."}],
            duration_minutes=60, wapef_deep_hope="", week_number=1,
        )
        base.update(over)
        for k, v in base.items():
            setattr(self, k, v)


def _prompt(**over):
    lp = _LP(**over)
    return _build_section_prompt(
        lp, over.pop("section", "assessment"),
        "Old assessment text here." if "current_content" not in over else over["current_content"],
        over.get("additional_context", ""), over.get("rewrite_mode", "suggest_another_version"))


def test_prompt_carries_the_full_contract():
    p = _prompt()
    assert "B7.1.1.1.1" in p                       # indicator code
    assert "Add whole numbers" in p                # indicator text
    assert "Learners can add whole numbers" in p   # objective
    assert "Mathematics" in p                      # subject
    assert "Basic 7" in p                          # class
    assert "60 minutes" in p                       # duration
    assert "counters" in p and "number cards" in p # resources
    assert "Old assessment text here." in p        # ORIGINAL section content
    assert "worked example" in p                   # current teaching approach
    assert "NaCCA" in p                            # curriculum evidence block
    assert "CURRICULUM EVIDENCE" in p
    assert "never renumber" in p                   # preservation rules
    assert '{"assessment":' in p                   # JSON output contract


def test_prompt_includes_the_teacher_instruction():
    p = _prompt(additional_context="Use the market context for examples.")
    assert "TEACHER INSTRUCTION: Use the market context" in p


def test_make_more_practical_mode_changes_the_instruction():
    suggest = _prompt(rewrite_mode="suggest_another_version")
    practical = _prompt(rewrite_mode="make_more_practical")
    assert "ANOTHER VERSION" in suggest
    assert "MORE PRACTICAL" in practical
    assert suggest != practical


def test_prompt_preserves_wapef_when_present():
    p = _prompt(wapef_deep_hope="Stewardship of resources")
    assert "WAPEF deep hope to honour" in p
    assert "Stewardship of resources" in p


def test_prompt_states_when_no_exemplar_exists():
    """Empty retrieval is valid: the prompt must say so, and forbid the AI
    from inventing curriculum content."""
    p = _prompt(indicator_codes=["X9.9.9.9.9"],
                indicators=["X9.9.9.9.9 Do something not in the corpus"])
    assert "No structured curriculum exemplar is on file" in p
    assert "do not invent" in p


def test_main_activities_contract_asks_for_phases():
    p = _prompt(section="main_activities")
    assert "main_learning" in p
    assert "duration_minutes" in p


def test_prompt_uses_grounded_local_examples_only():
    p = _prompt()
    assert "Ghanaian" in p
    assert "No ICT, projector or smartboard" in p


# ── Provider dispatch ────────────────────────────────────────────────────────

class _StructuredProvider:
    """A real provider shape: implements generate_structured."""

    def generate_structured(self, prompt: str) -> dict:
        return {"assessment": "New AI assessment text with concrete steps."}

    def generate_lesson_content(self, **kwargs):
        raise AssertionError("legacy path must not be used here")


class _LegacyProvider:
    """A provider shape without the structured override."""

    def generate_lesson_content(self, **kwargs):
        return {"assessment": "Legacy whole-lesson assessment text."}


def test_structured_provider_receives_the_prompt_verbatim():
    captured = []

    class P(_StructuredProvider):
        def generate_structured(self, prompt):
            captured.append(prompt)
            return {"assessment": "AI text."}

    out = _section_generation(P(), "THE PROMPT", {"indicator": "ind"})
    assert out == {"assessment": "AI text."}
    assert captured == ["THE PROMPT"]


def test_provider_without_structured_falls_back_to_legacy():
    out = _section_generation(_LegacyProvider(), "ignored",
                              {"indicator": "ind", "strand": "s"})
    assert out["assessment"] == "Legacy whole-lesson assessment text."


def test_mock_provider_falls_back_to_legacy():
    """MagicMock (how the existing suites stub providers) has no
    generate_structured CLASS attribute, so it keeps the legacy call."""
    from unittest.mock import MagicMock
    m = MagicMock()
    _section_generation(m, "prompt", {"indicator": "x"})
    m.generate_lesson_content.assert_called_once_with(indicator="x")


# ── End-to-end over the router ───────────────────────────────────────────────

def _make_lesson(db, owner, section_value="Old assessment text here."):
    from src.database import SchemeDB, LessonPlanDB, GenerationJobDB, generate_id
    scheme = SchemeDB(id=generate_id(), owner_id=owner.id, filename="s.docx",
                      subject="Mathematics", class_level="Basic 7")
    db.add(scheme)
    db.commit()
    job = GenerationJobDB(id=generate_id(), owner_id=owner.id, scheme_id=scheme.id,
                          status="completed")
    db.add(job)
    db.flush()
    lp = LessonPlanDB(id=generate_id(), job_id=job.id, owner_id=owner.id,
                      scheme_id=scheme.id, week_number=1, lesson_sequence=1,
                      class_level="Basic 7", subject="Mathematics",
                      duration_minutes=60,
                      strand="Number", sub_strand="Number",
                      indicators=["B7.1.1.1.1 Add whole numbers"],
                      indicator_codes=["B7.1.1.1.1"],
                      learning_objectives=[{"description": "Learners can add whole numbers."}],
                      teaching_learning_resources=["counters"],
                      main_activities=[{"description": "Teacher works through one example."}],
                      assessment=section_value,
                      class_assignment="Old class assignment text here.",
                      home_assignment="Old home assignment text here.")
    db.add(lp)
    db.commit()
    return lp


class TestRewriteOverRouter:
    @pytest.mark.asyncio
    async def test_successful_rewrite_returns_ai_text_for_new_sections(self, db):
        from tests.conftest import make_entitled_teacher

        u, _school, _lic = make_entitled_teacher(db, email="ai_rw_success@t.test")
        lp = _make_lesson(db, u)
        provider = _StructuredProvider()
        provider.is_available = lambda: True
        provider.get_name = lambda: "structured"
        provider.model = "test-model"
        with patch.object(air, "get_provider", return_value=provider):
            res = await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="class_assignment",
                    ai_mode="gemini", rewrite_mode="make_more_practical"),
                u, db)
        assert res.new_content.startswith("New AI assessment")
        assert res.previous_content == "Old class assignment text here."
        assert res.section == "class_assignment"
        assert res.source == "ai"

    @pytest.mark.asyncio
    async def test_structured_provider_needs_a_dict_payload(self, db):
        """A provider whose generate_structured returns None/dict-like junk is
        a provider failure — the deterministic content is preserved."""
        from tests.conftest import make_entitled_teacher

        class Broken:
            last_error = None

            def generate_structured(self, prompt):
                return None

        u, _school, _lic = make_entitled_teacher(db, email="ai_rw_fail@t.test")
        lp = _make_lesson(db, u)
        broken = Broken()
        broken.is_available = lambda: True
        broken.get_name = lambda: "broken"
        with patch.object(air, "get_provider", return_value=broken):
            with pytest.raises(HTTPException) as e:
                await air.regenerate_section(
                    air.SectionRegenerateRequest(
                        lesson_plan_id=lp.id, section="assessment", ai_mode="gemini"),
                    u, db)
        assert e.value.status_code == 502
        db.refresh(lp)
        assert lp.assessment == "Old assessment text here."

    @pytest.mark.asyncio
    async def test_home_assignment_rewrites_two_of_two(self, db):
        from tests.conftest import make_entitled_teacher

        u, _school, _lic = make_entitled_teacher(db, email="ai_rw_home@t.test")
        lp = _make_lesson(db, u)
        provider = _StructuredProvider()
        provider.is_available = lambda: True
        provider.get_name = lambda: "structured"
        provider.model = "m"
        with patch.object(air, "get_provider", return_value=provider):
            res = await air.regenerate_section(
                air.SectionRegenerateRequest(
                    lesson_plan_id=lp.id, section="home_assignment", ai_mode="gemini"),
                u, db)
        assert res.section == "home_assignment"
        assert res.previous_content == "Old home assignment text here."
