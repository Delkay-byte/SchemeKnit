"""Ghanaian context bank — coverage, stability and wiring (Priority 2 §13).

The subject-level bank (`GHANA_CONTEXT_BY_SUBJECT` / `ghana_context_for`)
must cover every pedagogy profile with multiple examples, resolve subject
values and aliases deterministically, and back-stop activities that carry
no task-specific framing of their own.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.curriculum.activity_library import (
    ACTIVITIES,
    GHANA_CONTEXT_BY_SUBJECT,
    ghana_context_for,
)
from src.curriculum.pedagogy import SUBJECT_PROFILES, SUBJECT_TO_PROFILE


class TestCoverage:
    def test_all_pedagogy_profiles_have_context(self):
        missing = [k for k in SUBJECT_PROFILES if k not in GHANA_CONTEXT_BY_SUBJECT]
        assert missing == [], f"profiles without Ghana context: {missing}"

    def test_every_profile_has_at_least_two_examples(self):
        thin = {k: len(v) for k, v in GHANA_CONTEXT_BY_SUBJECT.items()
                if len(v) < 2}
        assert thin == {}, f"profiles with <2 examples: {thin}"

    def test_examples_are_non_empty_sentences(self):
        for key, options in GHANA_CONTEXT_BY_SUBJECT.items():
            for example in options:
                assert isinstance(example, str) and example.strip(), key
                assert len(example.split()) >= 6, (key, example)
                assert example.strip().endswith("."), (key, example)


class TestResolution:
    def test_profile_keys_resolve(self):
        for key in SUBJECT_PROFILES:
            assert ghana_context_for(key), key

    def test_raw_subject_values_resolve(self):
        for value in ("Social Studies", "Creative Arts and Design",
                      "Career Technology", "Language and Literacy",
                      "Our World Our People", "Numeracy", "Physical Development"):
            assert ghana_context_for(value), value

    def test_unknown_subject_returns_empty(self):
        assert ghana_context_for("") == ""
        assert ghana_context_for("quantum basket weaving") == ""

    def test_variant_rotation_is_deterministic_and_bounded(self):
        first = ghana_context_for("mathematics", variant=0)
        again = ghana_context_for("mathematics", variant=0)
        assert first == again
        options = GHANA_CONTEXT_BY_SUBJECT["mathematics"]
        for variant in range(len(options) * 3):
            picked = ghana_context_for("mathematics", variant=variant)
            assert picked == options[variant % len(options)], variant

    def test_aliases_map_to_their_profiles_profile(self):
        assert (ghana_context_for("language and literacy")
                == ghana_context_for("early_childhood", variant=0))
        assert (ghana_context_for("numeracy")
                == ghana_context_for("mathematics", variant=0))


class TestActivityFallback:
    def test_bank_activities_without_framing_are_backstopped(self):
        """Whichever activities stay generic must still resolve a subject
        clause through the fallback."""
        uncovered = [a.id for a in ACTIVITIES if not a.ghana_context]
        for subject_key in SUBJECT_PROFILES:
            assert ghana_context_for(subject_key), (uncovered, subject_key)

    def test_wired_into_builder_for_generic_activities(self):
        """A lesson whose activity carries no ghana_context still builds
        and the subject-level clause is available as the fallback."""
        from datetime import date

        from src.curriculum.lesson_builder import build_lesson
        from src.models import (
            AIMode, AllocatedIndicator, ClassLevel, Subject, TermConfig,
        )

        cfg = TermConfig(
            scheme_of_work_id="t", academic_year="2026/2027",
            term="First Term", class_level=ClassLevel.BASIC_7,
            subject=Subject.MATHEMATICS,
            term_start_date=date(2026, 9, 7),
            term_end_date=date(2026, 12, 18),
            lessons_per_week=1, lesson_duration_minutes=40,
            teaching_days=[0], holidays=[], ai_mode=AIMode.OFF,
            school_name="S", teacher_name="T",
        )
        alloc = AllocatedIndicator(
            indicator_code="B7.1.1.1.1",
            indicator_description="B7.1.1.1.1 Add like fractions with "
                                  "denominators up to 12",
            content_standard_code="B7.1.1",
            content_standard_description="Number and numeration",
            strand="Number", sub_strand="Fractions",
            week_number=1, source_resources=["Fraction strips"],
            lesson_date=date(2026, 9, 7), period_index=1,
            allocated=True, teaching_week=1,
        )
        lp = build_lesson(alloc, cfg, "t")
        assert lp.lesson_topic
        assert lp.assessment

    def test_subject_bank_reaches_real_lesson_output(self, monkeypatch):
        """The fallback must be visible in the lesson, not just resolvable.

        Force the selected activity to carry no activity-level Ghana framing
        (the three library patterns that legitimately have none behave the
        same way), so the builder's subject fallback is the only source of
        the clause; it must appear in the deterministic assessment and be
        stable for the same input.
        """
        from dataclasses import replace
        from datetime import date

        from src.curriculum import activity_library as al
        from src.curriculum.lesson_builder import build_lesson
        from src.models import (
            AIMode, AllocatedIndicator, ClassLevel, Subject, TermConfig,
        )

        real_select = al.select_activity
        monkeypatch.setattr(
            al, "select_activity",
            lambda *a, **kw: replace(real_select(*a, **kw), ghana_context=()),
        )

        cfg = TermConfig(
            scheme_of_work_id="t", academic_year="2026/2027",
            term="First Term", class_level=ClassLevel.BASIC_7,
            subject=Subject.MATHEMATICS,
            term_start_date=date(2026, 9, 7),
            term_end_date=date(2026, 12, 18),
            lessons_per_week=1, lesson_duration_minutes=60,
            teaching_days=[0], holidays=[], ai_mode=AIMode.OFF,
            school_name="S", teacher_name="T",
        )

        def lesson():
            alloc = AllocatedIndicator(
                indicator_code="B7.1.1.1.1",
                indicator_description=(
                    "B7.1.1.1.1 Demonstrate how to add like fractions"),
                content_standard_code="B7.1.1",
                content_standard_description="Number and numeration",
                strand="Number", sub_strand="Fractions",
                week_number=1, source_resources=["Fraction strips"],
                lesson_date=date(2026, 9, 7), period_index=1,
                allocated=True, teaching_week=1,
            )
            return build_lesson(alloc, cfg, "t")

        clause = ghana_context_for("Mathematics", variant=0)
        first = lesson()
        blob = " ".join(i.prompt for i in first.assessment_items)
        # Phase 6.3: an ordinary word after a colon is lowercased in the
        # composed teacher-facing prompt ("Apply it: use Ghanaian …"), so the
        # bank clause matches case-insensitively.
        assert clause.lower() in blob.lower(), blob
        # Same inputs → identical composed clause (deterministic selection).
        blob2 = " ".join(i.prompt for i in lesson().assessment_items)
        assert blob.lower() == blob2.lower()
