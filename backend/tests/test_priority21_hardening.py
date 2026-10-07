"""
Priority 2.1 — deterministic lesson-authoring hardening regressions.

One focused hardening pass: bigger activity/resource/subject banks, verb and
progression sensitivity, variation across a batch, objective cleanup and
resource realism — so an ordinary lesson is usable WITHOUT the AI rewrite.

Sections (matching docs/DETERMINISTIC_LESSON_HARDENING_REPORT.md):
  A. Activity library scale, metadata and deterministic selection (§C)
  B. Verb-matched assessment coverage (§C)
  C. Subject strategy coverage — PHE / history / early-childhood (§D)
  D. Objective shaping — artifacts, generic leads, gerunds, French (§E)
  E. Resource realism — impossible equipment filtered, source kept (§F)
  F. Timing invariant across 30–80 minutes (§G)
  G. Progression — fingerprints, repeat addenda, starter variants (§18)
"""

import re
from datetime import date

import pytest

from src.curriculum.activity_library import (
    ACTIVITIES, ASSESSMENT_FOR_VERB, assessment_for_verb, select_activity,
)
from src.curriculum.activity_library import ACTIVITIES as _LIB


# ── A. Activity library ──────────────────────────────────────────────────────


class TestActivityLibraryScale:
    def test_library_carries_at_least_27_structures(self):
        assert len(ACTIVITIES) >= 27, (
            "the hardened library must cover the curriculum's action verbs "
            f"beyond the original eight/nine structures, found {len(ACTIVITIES)}"
        )

    def test_every_entry_declares_types_and_complete_metadata(self):
        from src.curriculum.indicator_interpreter import ACTIVITY_KEYWORDS

        ids = set()
        for a in ACTIVITIES:
            assert a.id not in ids, f"duplicate activity id {a.id}"
            ids.add(a.id)
            assert a.activity_types, f"{a.id} declares no activity_types"
            unknown = set(a.activity_types) - set(ACTIVITY_KEYWORDS)
            assert not unknown, f"{a.id} uses non-keyword types {unknown}"
            assert a.action_verbs, f"{a.id} declares no action verbs"
            assert all(v == v.strip().lower() and v for v in a.action_verbs)
            assert a.subjects == tuple(s for s in a.subjects if s.strip())
            for field in ("teacher_action", "learner_action", "materials",
                          "evidence", "assessment", "support", "challenge"):
                assert str(getattr(a, field)).strip(), f"{a.id}: empty {field}"
            assert a.stages and set(a.stages) <= {"first", "repeat"}

    def test_selection_is_deterministic(self):
        cases = [
            (["classify"], "science", "classification"),
            (["retell"], "english", "reading"),
            (["troubleshoot"], "ict", "problem_solving"),
            (["observe"], "phe", "observation"),
        ]
        for verbs, subject, hint in cases:
            first = select_activity(verbs, subject, "first", hint)
            for _ in range(3):
                again = select_activity(verbs, subject, "first", hint)
                assert again.id == first.id

    def test_new_structures_are_reachable_for_their_verbs(self):
        """Every bank entry must win for its own verb + subject + hint."""
        pairs = {
            ("retell", "english", "reading"): "guided_reading_comprehension",
            ("compose", "english", "writing"): "guided_writing_composition",
            ("listen", "english", "reading"): "listen_and_respond",
            ("sing", "creative_arts", "creation"): "sing_and_perform",
            ("colour", "early_childhood", "practical"): "trace_colour_make",
            ("count", "early_childhood", "problem_solving"): "count_and_practise",
            ("label", "science", "practical"): "label_annotate_diagram",
            ("locate", "social_studies", "observation"): "map_and_locate",
            ("argue", "social_studies", "discussion"): "debate_and_argue",
            ("assess", "mathematics", "reflection"): "assess_and_review",
            ("research", "social_studies", "investigation"): "research_and_report",
            ("sequence", "ict", "practical"): "sequence_the_steps",
            ("troubleshoot", "ict", "problem_solving"): "troubleshoot_and_fix",
            ("play", "phe", "practical"): "game_and_drill",
            ("reflect", "rme", "reflection"): "reflect_and_discuss",
            ("present", "creative_arts", "discussion"): "present_and_share",
            ("critique", "creative_arts", "reflection"): "critique_and_improve",
            ("observe", "science", "observation"): "guided_investigation",
            ("summarise", "english", "reading"): "summarise_and_restate",
        }
        for (verb, subject, hint), expected in pairs.items():
            got = select_activity([verb], subject, "first", hint)
            assert got.id == expected, (
                f"{verb} + {subject} + {hint}: expected {expected}, got {got.id}"
            )

    def test_original_winners_are_unchanged_for_original_verbs(self):
        """Churn guard: the structures that already won still win."""
        pairs = {
            ("classify", "science", "classification"): "guided_investigation",
            ("calculate", "mathematics", "problem_solving"): "work_examples_practice",
            ("design", "creative_arts", "creation"): "design_create",
            ("role play", "rme", "practical"): "role_play_practice",
            ("identify", "ict", "observation"): "identify_recognise",
            ("demonstrate", "ict", "demonstration"): "demonstrate_practice",
        }
        for (verb, subject, hint), expected in pairs.items():
            got = select_activity([verb], subject, "first", hint)
            assert got.id == expected, (
                f"{verb} + {subject}: churn — expected {expected}, got {got.id}"
            )

    def test_unknown_evidence_falls_back_to_the_first_structure(self):
        assert select_activity([], "", "first", "").id == _LIB[0].id


# ── B. Verb-matched assessment ───────────────────────────────────────────────


class TestAssessmentForVerb:
    def test_every_template_is_a_non_empty_sentence_with_focus(self):
        assert ASSESSMENT_FOR_VERB, "assessment bank emptied"
        for verb, template in ASSESSMENT_FOR_VERB.items():
            assert verb == verb.strip().lower() and verb, f"bad key {verb!r}"
            assert template.strip(), f"{verb} maps to an empty template"
            assert "{focus}" in template, f"{verb}: template ignores the focus"
            assert "compare_" not in ASSESSMENT_FOR_VERB, "dead compare_ key"

    def test_unclaimed_curriculum_verbs_now_have_a_check(self):
        for verb in ("add", "subtract", "multiply", "divide", "count",
                     "install", "assess", "relate", "recognise", "sing",
                     "summarise", "retell", "label", "locate", "sequence",
                     "troubleshoot", "observe", "reflect", "present",
                     "critique"):
            assert verb in ASSESSMENT_FOR_VERB, f"no assessment for {verb}"

    def test_assessment_renders_the_focus(self):
        out = assessment_for_verb("classify", "the parts of a computer")
        assert out and "{focus}" not in out
        assert "the parts of a computer" in out
        assert assessment_for_verb("unknownverb", "x") == ""


# ── C. Subject strategy coverage ─────────────────────────────────────────────


class TestSubjectStrategies:
    def test_every_mapped_strategy_exists(self):
        from src.curriculum.indicator_interpreter import (
            SUBJECT_STRATEGIES, SUBJECT_TO_STRATEGY,
        )
        for subject_key, strategy in SUBJECT_TO_STRATEGY.items():
            assert strategy in SUBJECT_STRATEGIES, (
                f"{subject_key} maps to missing strategy {strategy}"
            )

    @pytest.mark.parametrize("subject,expect", [
        ("Physical and Health Education", "phe"),
        ("PHE", "phe"),
        ("Physical Development", "phe"),
        ("History", "social_studies"),
        ("Our World Our People", "social_studies"),
        ("Language and Literacy", "early_childhood"),
        ("General Agriculture", "science"),
        ("Business Management", "career_technology"),
        ("Numeracy", "mathematics"),
    ])
    def test_subject_names_map_to_a_strategy(self, subject, expect):
        from src.curriculum.indicator_interpreter import activity_preference_for
        from src.curriculum.indicator_interpreter import SUBJECT_TO_STRATEGY
        from src.curriculum.indicator_interpreter import SUBJECT_ACTIVITY_PREFERENCE

        assert SUBJECT_TO_STRATEGY[subject.lower().strip()] == expect
        assert activity_preference_for(subject) == \
            SUBJECT_ACTIVITY_PREFERENCE[expect]

    def test_phe_indicator_uses_the_phe_preference(self):
        from src.curriculum import Indicator
        from src.curriculum.indicator_interpreter import (
            SUBJECT_ACTIVITY_PREFERENCE, interpret_indicator,
        )
        ind = Indicator(
            code="B7/JHS1.1.1.1.1",
            exact_text="B7/JHS1.1.1.1.1 Demonstrate a warm-up exercise",
            description="Demonstrate a warm-up exercise",
            source_week=1,
            source_subject="Physical and Health Education",
        )
        first = interpret_indicator(ind, "Physical and Health Education")
        assert first.activity_type in SUBJECT_ACTIVITY_PREFERENCE["phe"]
        again = interpret_indicator(ind, "Physical and Health Education")
        assert again.activity_type == first.activity_type

    def test_phe_and_history_get_subject_context_not_the_default(self):
        from src.curriculum.indicator_interpreter import _derive_subject_context
        phe = _derive_subject_context("Physical and Health Education")
        assert "movement" in phe.lower() or "games" in phe.lower()
        assert phe != "Use contextually appropriate methods for Ghanaian classrooms."
        history = _derive_subject_context("History")
        assert "ghanaian" in history.lower()
        early = _derive_subject_context("Language and Literacy")
        assert "play" in early.lower()

    def test_no_suggested_resource_carries_whitespace_artifacts(self):
        from src.curriculum.indicator_interpreter import SUBJECT_STRATEGIES
        for key, strategy in SUBJECT_STRATEGIES.items():
            for r in strategy.get("resources", []):
                assert r == r.strip() and r, f"{key}: resource {r!r} not clean"


# ── D. Objective shaping ─────────────────────────────────────────────────────


class TestObjectiveShaping:
    def test_dangling_connector_is_trimmed_from_the_focus(self):
        from src.curriculum.lesson_builder import _first_clause
        out = _first_clause("B7.1.2.1.1 Round numbers to the nearest ten using.")
        assert not out.lower().rstrip().endswith(("using", "with", "from"))
        assert out.strip() and "  " not in out

    def test_generic_lead_becomes_a_measurable_verb(self):
        from src.curriculum.lesson_builder import _learner_phrase
        out = _learner_phrase("Explore the parts of a computer", "ICT")
        assert out.startswith("Learners can Explain"), out
        assert "the parts of a computer" in out

    def test_gerund_lead_becomes_its_base_verb(self):
        from src.curriculum.lesson_builder import _learner_phrase
        out = _learner_phrase("Demonstrating the fold of a map",
                              "Creative Arts and Design")
        assert out.startswith("Learners can Demonstrate"), out

    @pytest.mark.parametrize("subject,indicator", [
        ("Religious and Moral Education", "Attributes of God in daily life"),
        ("Physical and Health Education", "Food nutrients needed by the body"),
        ("Mathematics", "Place value of four-digit numbers"),
    ])
    def test_verbless_lead_receives_a_subject_verb(self, subject, indicator):
        from src.curriculum.lesson_builder import _learner_phrase, _lead_verb_lexicon
        out = _learner_phrase(indicator, subject)
        assert out.startswith("Learners can ")
        lead = out.split(" ", 2)[2].split(" ", 1)[0].lower()
        assert lead in _lead_verb_lexicon(), f"{lead!r} is not a measurable verb"
        assert indicator.split()[0].lower() not in (lead,)

    def test_real_lead_verb_is_kept_verbatim(self):
        from src.curriculum.lesson_builder import _learner_phrase
        out = _learner_phrase("Classify animals into groups", "Science")
        assert out == "Learners can Classify animals into groups"

    def test_french_prose_is_never_rephrased(self):
        from src.curriculum.lesson_builder import _learner_phrase
        src = "Décrire les parties du corps en français"
        out = _learner_phrase(src, "French")
        assert out == f"Learners can {src}"

    @pytest.mark.parametrize("indicator,subject", [
        ("B7.1.1.1.1 : Discuss the water cycle", "Science"),
        ("Explore and talk about communication skills", "English Language"),
        ("Demonstrating safe handling of laboratory glassware", "Science"),
        ("Attributes of God in daily life", "Religious and Moral Education"),
    ])
    def test_objective_shape_is_artifact_free(self, indicator, subject):
        from src.curriculum.lesson_builder import _learner_phrase
        out = _learner_phrase(indicator, subject)
        assert out.startswith("Learners can ")
        for artifact in (" :", "  ", " .", "..", " :", "\t"):
            assert artifact not in out, f"{artifact!r} leaked into {out!r}"
        assert not re.match(r"^[A-Za-z]{0,2}\d+\.\d", out[len("Learners can "):])
        generic = {"explore", "understand", "discuss", "know", "learn", "talk"}
        assert out.split(" ", 2)[2].split(" ", 1)[0].lower() not in generic


# ── E. Resource realism ──────────────────────────────────────────────────────


def _cfg(subject=None, duration=60):
    from src.models import ClassLevel, Subject, TermConfig
    return TermConfig(
        scheme_of_work_id="s", academic_year="2026/2027", term="First Term",
        class_level=ClassLevel.BASIC_7,
        subject=subject or Subject.ICT,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=2, lesson_duration_minutes=duration,
        teaching_days=[0, 2], holidays=[],
    )


def _alloc(text, resources=None, week=1, code="B7.1.1.1.2"):
    from src.models import AllocatedIndicator
    return AllocatedIndicator(
        indicator_code=code,
        indicator_description=text,
        content_standard_code="B7.1.1.1",
        content_standard_description="B7.1.1.1 Learners describe devices",
        strand="Introduction to Computing",
        sub_strand="Components of a computer",
        week_number=week,
        source_resources=list(resources or ["Touchscreen", "Mouse", "Keyboard"]),
        lesson_date=date(2026, 9, 7), period_index=1, allocated=True,
        teaching_week=week,
    )


class TestResourceRealism:
    @pytest.mark.parametrize("resource,subject,expect", [
        ("projector", "Religious and Moral Education", False),
        ("internet resources", "Creative Arts and Design", False),
        ("smart board", "Social Studies", False),
        ("laboratory equipment", "Science", False),
        ("chart", "Science", True),
        ("counters and bundles of sticks", "Mathematics", True),
        ("projector", "ICT", True),
        ("laptop", "Computing", True),
        ("internet", "Digital Literacy", True),
    ])
    def test_impossible_resources_filtered_except_digital_subjects(
            self, resource, subject, expect):
        from src.curriculum.lesson_builder import _resource_is_available
        assert _resource_is_available(resource, subject) is expect

    def test_non_ict_lesson_never_requires_the_banned_equipment(self):
        from src.curriculum.lesson_builder import _IMPOSSIBLE_RESOURCE_RE, build_lesson
        from src.models import Subject
        lp = build_lesson(
            _alloc("B7.1.1.1.2 Discuss the features of a healthy community",
                   resources=["projector", "chart", "internet resources"]),
            _cfg(subject=Subject.RME), "s")
        assert lp.teaching_learning_resources, "display resources must not be empty"
        for r in lp.teaching_learning_resources:
            assert not _IMPOSSIBLE_RESOURCE_RE.search(r), (
                f"impossible resource {r!r} shown as required"
            )
        # source authority: the scheme's own wording stays verbatim
        assert lp.source_tlrs == ["projector", "chart", "internet resources"]

    def test_ict_lesson_keeps_digital_resources(self):
        from src.curriculum.lesson_builder import build_lesson
        lp = build_lesson(
            _alloc("B7.1.1.1.2 Demonstrate how to start a computer safely",
                   resources=["projector", "computer"]),
            _cfg(subject=None), "s")
        assert any("projector" in r for r in lp.teaching_learning_resources), (
            "computing lessons are the subject matter of digital equipment"
        )
        assert lp.source_tlrs == ["projector", "computer"]


# ── F. Timing invariant ──────────────────────────────────────────────────────


class TestTimingStress:
    @pytest.mark.parametrize("duration", list(range(30, 81, 5)))
    def test_stored_timeline_sums_exactly_to_the_duration(self, duration):
        from src.curriculum.lesson_builder import build_lesson
        from src.models import Subject
        lp = build_lesson(
            _alloc("B7.1.1.1.2 Classify input and output devices"),
            _cfg(subject=Subject.RME, duration=duration), "s")
        assert lp.duration_minutes == duration
        assert len(lp.main_activities) >= 3
        for rows in (lp.main_activities, lp.learner_activities,
                     lp.teacher_activities):
            total = sum(r.duration_minutes for r in rows)
            assert total == duration, (
                f"{duration} min lesson: {len(rows)} rows sum to {total}"
            )
            assert all(r.duration_minutes >= 1 for r in rows)


# ── G. Progression (§18) ─────────────────────────────────────────────────────


class TestProgression:
    def test_fingerprint_records_the_indicator_code(self):
        from src.curriculum.lesson_builder import build_lesson
        from src.curriculum.variation import fingerprint_lesson
        lp = build_lesson(
            _alloc("B7.1.1.1.2 Classify input and output devices"),
            _cfg(), "s")
        fp = fingerprint_lesson(lp, pattern_id="p")
        assert fp.indicator_code == "B7.1.1.1.2"

    def test_repeat_addenda_rotate_and_format(self):
        from src.curriculum.lesson_builder import _REPEAT_ADDENDUMS, _repeat_addendum
        first = _repeat_addendum("learner", "fractions", 1)
        assert first == _REPEAT_ADDENDUMS["learner"][0].strip()
        assert _repeat_addendum("learner", "fractions", 2) == \
            _REPEAT_ADDENDUMS["learner"][1].strip()
        # cycle — the 4th occurrence lands back on an earlier variant
        assert _repeat_addendum("learner", "fractions", 4) == \
            _REPEAT_ADDENDUMS["learner"][0].strip()
        for prior in (1, 2, 3, 4, 7):
            out = _repeat_addendum("conclusion", "the water cycle", prior)
            assert "{focus_short}" not in out
            assert "the water cycle" in out

    def test_starter_variants_start_from_the_established_text(self):
        from src.curriculum.lesson_builder import _STARTER_VARIANTS
        assert _STARTER_VARIANTS[0] == "", (
            "variant 1 must be byte-identical to the established opener"
        )
        assert len(set(_STARTER_VARIANTS)) == len(_STARTER_VARIANTS)

    def test_second_occurrence_of_a_code_shifts_to_repeat_stage(self):
        from src.curriculum.lesson_builder import build_lesson
        from src.curriculum.patterns import PATTERNS
        from src.curriculum.variation import BatchHistory
        from src.models import Subject

        history = BatchHistory(scheme_id="s", subject="Mathematics")
        text = "B7.1.1.1.2 Classify input and output devices"
        cfg = _cfg(subject=Subject.ICT)
        pattern = PATTERNS[0]

        first = build_lesson(_alloc(text, week=1), cfg, "s",
                             pattern=pattern, batch_history=history)
        assert len(history.fingerprints) == 1
        assert history.fingerprints[0].indicator_code == "B7.1.1.1.2"

        second = build_lesson(_alloc(text, week=2), cfg, "s",
                              pattern=pattern, batch_history=history)
        # The repeat stage must be observable: the application addendum or the
        # alternate opener marks the revisit; the indicator/week never change.
        assert second.indicator_codes == first.indicator_codes
        assert second.conclusion != first.conclusion, (
            "repeat stage must append the application addendum to the closing"
        )
        assert second.class_assignment != first.class_assignment or \
            "Apply it" in second.conclusion
        # starter variants: same evidence in, byte-same base out
        assert second.starter_activity.startswith(
            first.starter_activity[:60]), "starter base must be preserved"

    def test_repeat_stage_detection_needs_history_and_pattern(self):
        from src.curriculum.lesson_builder import build_lesson
        text = "B7.1.1.1.2 Classify input and output devices"
        lp = build_lesson(_alloc(text), _cfg(), "s")
        # no history, no pattern: the first-occurrence output stays pinned
        assert lp.starter_activity.strip()
        assert lp.conclusion.strip()
