"""
Official-curriculum exemplar corpus + deterministic pedagogy (PHASE 1–7, 14).

What these tests defend:

* every corpus record carries real provenance and is DERIVED, not a copied
  sentence from an official document;
* an indicator code resolves only inside its own subject (B7.1.1.1.1 is the
  first Strand-1 indicator in Computing, Mathematics AND Physical Education and
  Health — one must never answer for another);
* the five real Computing B7 indicators produce genuinely different lessons
  (the defect that made every one of them read "Learners can explore and talk
  about Components of Computers and Computer Systems");
* the deterministic lesson is classroom-usable with no AI at all.
"""

from datetime import date

import pytest


# ── Corpus integrity ────────────────────────────────────────────────────────


class TestCorpusIntegrity:
    def test_corpus_has_records_across_the_priority_subjects(self):
        from src.curriculum.exemplars import all_records

        subjects = {r.subject for r in all_records()}
        for required in (
            "Computing",
            "Mathematics",
            "Science",
            "English Language",
            "Religious and Moral Education",
            "Social Studies",
            "Career Technology",
            "Creative Arts and Design",
            "Physical Education and Health",
        ):
            assert required in subjects, f"no exemplar coverage for {required}"

    def test_every_record_carries_provenance(self):
        from src.curriculum.exemplars import all_records

        for r in all_records():
            assert r.source_title.strip(), f"{r.indicator_code}: no source_title"
            assert r.source_url.startswith("http"), f"{r.indicator_code}: no source_url"
            assert r.source_version.strip(), f"{r.indicator_code}: no source_version"
            assert r.provenance.strip(), f"{r.indicator_code}: no provenance note"
            # An official record must point at the curriculum authority, never a
            # third-party lesson-plan site.
            assert "nacca.gov.gh" in r.source_url or "curriculumresources.edu.gh" in r.source_url

    def test_records_are_derived_not_copied_official_sentences(self):
        """Stored patterns are authored structures, never verbatim copies.

        The guard list holds whole sentences taken from the official NaCCA
        documents read while deriving the corpus; none of them may appear in a
        stored field.
        """
        from src.curriculum.exemplars import all_records

        official_sentences = [
            "B7.1.1.1.2 Demonstrate understanding in the use of input devices",
            "Distinguish manual (e.g. keyboard, etc.) and automatic (e.g. barcode reader etc.) input devices.",
            "Explore the advantages and disadvantages of input devices",
            "Discuss features of fourth generation computers",
            "Explore the architecture of a processor",
            "Demonstrate the use of input devices in a computer laboratory/classroom.",
            "Show the desktop, tiles, taskbar.",
            "Demonstrate how to preview thumbnails",
            "Group materials into liquids, solids and gases.",
            "Create and complete a table to record the texture, appearance, colour and shape",
        ]
        for r in all_records():
            blob = " ".join([
                r.learning_focus,
                " ".join(r.exemplar_activity_patterns),
                " ".join(r.assessment_patterns),
                " ".join(r.assignment_patterns),
                r.class_assignment_pattern,
                r.home_assignment_pattern,
                " ".join(r.suitable_resource_patterns),
            ])
            for sentence in official_sentences:
                assert sentence not in blob, (
                    f"{r.indicator_code} reproduces official text: {sentence!r}")

    def test_learning_focus_is_a_short_derived_phrase(self):
        from src.curriculum.exemplars import all_records

        for r in all_records():
            words = r.learning_focus.split()
            assert 1 <= len(words) <= 12, (
                f"{r.indicator_code}: learning_focus is not a short phrase: "
                f"{r.learning_focus!r}")

    def test_every_record_has_action_verbs_and_activity_patterns(self):
        from src.curriculum.exemplars import all_records

        for r in all_records():
            assert r.curriculum_action_verbs, f"{r.indicator_code}: no action verbs"
            assert len(r.exemplar_activity_patterns) >= 2, (
                f"{r.indicator_code}: not enough activity patterns")
            assert r.assessment_patterns, f"{r.indicator_code}: no assessment pattern"
            assert r.class_assignment_pattern.strip()
            assert r.home_assignment_pattern.strip()

    def test_indicator_codes_are_unique_within_a_subject(self):
        from src.curriculum.exemplars import all_records

        seen = set()
        for r in all_records():
            key = (r.subject, r.indicator_code)
            assert key not in seen, f"duplicate record {key}"
            seen.add(key)


# ── Code resolution ─────────────────────────────────────────────────────────


class TestCodeResolution:
    @pytest.mark.parametrize("raw,expected", [
        # The shapes the official NaCCA CCP documents actually print.
        ("B7.1.1.1.1", "B7.1.1.1.1"),              # Computing / Maths / PHE
        ("b7.1.1.1.1", "B7.1.1.1.1"),              # case-insensitive
        ("B7/JHS1.1.1.1.1", "B7.1.1.1.1"),         # English-style    (sc) 1.1.1 / (ind) 1.1.1.1
        ("B7/JHS1.1.1.1", "B7.1.1.1"),             # English content standard
        ("B7/JHS1 1.1.1.1", "B7.1.1.1.1"),         # RME-style indicator
        ("B7/JHS1 1.1.1", "B7.1.1.1"),             # RME content standard
        ("  B7.1.1.2.1  ", "B7.1.1.2.1"),          # stray whitespace
    ])
    def test_all_real_code_shapes_normalize(self, raw, expected):
        from src.curriculum.exemplars import normalize_code

        assert normalize_code(raw) == expected

    def test_the_same_code_resolves_per_subject(self):
        from src.curriculum.exemplars import lookup_indicator

        computing = lookup_indicator("B7.1.1.1.1", "Computing")
        maths = lookup_indicator("B7.1.1.1.1", "Mathematics")
        phe = lookup_indicator("B7.1.1.1.1", "Physical and Health Education")
        assert computing and maths and phe
        assert computing.learning_focus != maths.learning_focus
        assert maths.learning_focus != phe.learning_focus
        assert computing.subject == "Computing"
        assert maths.subject == "Mathematics"

    def test_a_subject_is_never_answered_with_another_subjects_evidence(self):
        from src.curriculum.exemplars import lookup_indicator

        # Mathematics has no Strand-1 indicator .2 record.
        assert lookup_indicator("B7.1.1.1.2", "Mathematics") is None

    def test_subject_aliases_resolve(self):
        from src.curriculum.exemplars import lookup_indicator

        for alias in ("ICT", "Computing", "Information and Communication Technology"):
            assert lookup_indicator("B7.1.1.1.2", alias).learning_focus == (
                "Input devices: manual and automatic")
        for alias in ("RME", "Religious and Moral Education"):
            assert lookup_indicator("B7/JHS1 1.1.1.1", alias) is not None

    def test_an_unknown_code_returns_nothing(self):
        from src.curriculum.exemplars import lookup_indicator

        assert lookup_indicator("B9.4.3.1.2", "Computing") is None
        assert lookup_indicator("", "Computing") is None

    def test_an_ambiguous_code_without_a_subject_is_not_guessed(self):
        from src.curriculum.exemplars import lookup_indicator

        # Present in Computing, Mathematics and PHE: no subject, no answer.
        assert lookup_indicator("B7.1.1.1.1") is None


# ── Deterministic planning for the real Computing indicators (PHASE 3) ──────


def _computing_cfg():
    from src.models import ClassLevel, Subject, TermConfig

    return TermConfig(
        scheme_of_work_id="s", academic_year="2026/2027", term="First Term",
        class_level=ClassLevel.BASIC_7, subject=Subject.ICT,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=2, lesson_duration_minutes=60,
        teaching_days=[0, 2], holidays=[],
    )


_BS7_COMPUTING = [
    ("B7.1.1.1.1", "B7.1.1.1"),
    ("B7.1.1.1.2", "B7.1.1.1"),
    ("B7.1.1.1.4", "B7.1.1.1"),
    ("B7.1.1.2.1", "B7.1.1.2"),
    ("B7.1.1.2.2", "B7.1.1.2"),
]


def _computing_lesson(code: str, content_standard: str):
    from src.curriculum.lesson_builder import build_lesson
    from src.models import AllocatedIndicator

    alloc = AllocatedIndicator(
        indicator_code=code,
        # The real scheme's indicator column is CODE-ONLY (verified against the
        # exported BS7 lesson plans): this is the exact shape being remediated.
        indicator_description=code,
        content_standard_code=content_standard,
        content_standard_description=content_standard,
        strand="Introduction to Computing",
        sub_strand="Components of Computers and Computer Systems",
        week_number=1,
        source_resources=["Touchscreen", "Mouse", "Keyboard"],
        lesson_date=date(2026, 9, 7), period_index=1, allocated=True,
        teaching_week=1,
    )
    return build_lesson(alloc, _computing_cfg(), "s")


class TestRealComputingIndicators:
    def _lessons(self):
        return {code: _computing_lesson(code, cs)
                for code, cs in _BS7_COMPUTING}

    def test_all_five_are_covered_by_the_corpus(self):
        from src.curriculum.exemplars import lookup_indicator

        for code, _cs in _BS7_COMPUTING:
            assert lookup_indicator(code, "ICT") is not None, code

    def test_every_lesson_has_a_concrete_indicator_specific_objective(self):
        lessons = self._lessons()
        objectives = []
        for code, lp in lessons.items():
            objective = lp.learning_objectives[0].description
            assert objective.startswith("Learners can "), (code, objective)
            # The reported defect: one generic objective for every indicator.
            assert "explore and talk about" not in objective, (code, objective)
            objectives.append(objective)
        assert len(set(objectives)) == len(objectives), (
            "indicators share an objective: " + repr(objectives))

    def test_the_five_lessons_differ_in_every_teaching_block(self):
        lessons = self._lessons()
        codes = [c for c, _ in _BS7_COMPUTING]
        blocks = ["lesson_topic", "objective", "starter", "main",
                  "assessment", "class_assignment", "home_assignment"]
        signatures = {}
        for code in codes:
            lp = lessons[code]
            signatures[code] = {
                "lesson_topic": lp.lesson_topic,
                "objective": lp.learning_objectives[0].description,
                "starter": lp.starter_activity,
                "main": " | ".join(a.description for a in lp.main_activities),
                "assessment": lp.assessment,
                "class_assignment": lp.class_assignment,
                "home_assignment": lp.home_assignment,
            }
        for block in blocks:
            values = [signatures[c][block] for c in codes]
            assert len(set(values)) == len(values), (
                f"block {block!r} is identical across indicators: {values}")

    def test_each_lesson_carries_its_own_curriculum_vocabulary(self):
        lessons = self._lessons()
        assert "microchip" in " ".join(lessons["B7.1.1.1.1"].keywords).lower()
        assert "barcode reader" in " ".join(lessons["B7.1.1.1.2"].keywords).lower()
        assert "optical disc" in " ".join(lessons["B7.1.1.1.4"].keywords).lower()
        assert "taskbar" in " ".join(lessons["B7.1.1.2.1"].keywords).lower()
        assert "file extension" in " ".join(lessons["B7.1.1.2.2"].keywords).lower()

    def test_deterministic_lessons_are_detailed_enough_without_any_ai(self):
        """PHASE 5: every activity names the object, the teacher action and the
        learner action — no AI required."""
        lp = _computing_lesson("B7.1.1.1.2", "B7.1.1.1")
        assert lp.ai_generated is False
        assert len(lp.main_activities) >= 2
        for activity in lp.main_activities:
            assert len(activity.description) >= 120, activity.description
        assert len(lp.starter_activity) >= 100
        assert len(lp.class_assignment) >= 100
        assert len(lp.home_assignment) >= 80
        joined = " ".join(a.description for a in lp.main_activities).lower()
        # Named material and named learner action, not "learners practise".
        assert "keyboard" in joined or "barcode" in joined
        assert any(v in joined for v in ("sort", "demonstrate", "label", "write"))

    def test_no_generic_filler_phrase_dominates_the_lesson(self):
        """PHASE 5: the banned filler that used to fill the phases."""
        banned = [
            "watch and listen carefully",
            "complete the task",
            "work with your partner",
            "learners practise the concept",
        ]
        for code, cs in _BS7_COMPUTING:
            lp = _computing_lesson(code, cs)
            blob = " ".join([
                lp.starter_activity, lp.introduction,
                " ".join(a.description for a in lp.main_activities),
                lp.assessment, lp.class_assignment, lp.home_assignment,
            ]).lower()
            for phrase in banned:
                assert phrase not in blob, (code, phrase)

    def test_provenance_names_the_official_source(self):
        from src.curriculum.spine import lesson_provenance

        lp = _computing_lesson("B7.1.1.1.2", "B7.1.1.1")
        prov = lesson_provenance(lp)
        exemplar = prov.get("exemplar")
        assert exemplar, "no exemplar provenance recorded"
        assert "nacca.gov.gh" in exemplar["source_url"]
        assert exemplar["grounding"] == "Official NaCCA curriculum (derived)"
        assert exemplar["corpus_version"]

    def test_an_indicator_outside_the_corpus_reports_no_exemplar(self):
        from src.curriculum.spine import lesson_provenance

        lp = _computing_lesson("B9.4.3.1.2", "B9.4.3.1")
        assert lesson_provenance(lp).get("exemplar") is None


# ── Scheme prose still wins (source authority) ──────────────────────────────


class TestSourceAuthorityIsPreserved:
    def test_a_scheme_that_states_its_indicator_is_never_overridden(self):
        from src.curriculum.lesson_builder import build_lesson
        from src.models import AllocatedIndicator

        prose = "B7.1.1.1.2 Distinguish manual and automatic devices in the school ICT laboratory"
        alloc = AllocatedIndicator(
            indicator_code="B7.1.1.1.2",
            indicator_description=prose,
            content_standard_code="B7.1.1.1",
            content_standard_description="B7.1.1.1 Examine the parts of a computer",
            strand="Introduction to Computing",
            sub_strand="Components of Computers and Computer Systems",
            week_number=1, source_resources=["Keyboard"],
            lesson_date=date(2026, 9, 7), period_index=1, allocated=True,
            teaching_week=1,
        )
        lp = build_lesson(alloc, _computing_cfg(), "s")
        objective = lp.learning_objectives[0].description.lower()
        # The teacher's own indicator wording is the focus, not the corpus's.
        assert "distinguish manual and automatic devices" in objective
        # The corpus still supplies the pedagogy (activities are not generic).
        assert len(lp.main_activities) >= 2


# ── PHASE 14 — subject/indicator regression content cases ────────────────────

#: One real Strand-1/Sub-strand-1 lesson per priority subject, using the code
#: shape that subject's own NaCCA document prints.
#: (Subject enum, corpus subject alias, indicator code, content standard code)
_SUBJECT_CASES = [
    ("ICT", "ICT", "B7.1.1.1.2", "B7.1.1.1"),
    ("RME", "RME", "B7/JHS1 1.1.1.1", "B7/JHS1 1.1.1"),
    ("MATHEMATICS", "Mathematics", "B7.1.1.1.1", "B7.1.1.1"),
    ("SCIENCE", "Science", "B7/JHS1.1.1.1.1", "B7/JHS1.1.1.1"),
    ("ENGLISH", "English Language", "B7/JHS1.1.1.1.1", "B7/JHS1.1.1.1"),
    ("SOCIAL_STUDIES", "Social Studies", "B7/JHS1.1.1.1.1", "B7/JHS1.1.1.1"),
    ("CAREER_TECHNOLOGY", "Career Technology", "B7/JHS1.1.1.1.1", "B7/JHS1.1.1.1"),
    ("CREATIVE_ARTS", "Creative Arts", "B7/JHS1 1.1.1.1", "B7/JHS1 1.1.1"),
    ("PHE", "PHE", "B7.1.1.1.1", "B7.1.1.1"),
]


def _subject_lesson(subject_enum: str, code: str, content_standard: str):
    """A real code-only scheme entry, built through the production planner."""
    from src.curriculum.lesson_builder import build_lesson
    from src.models import AllocatedIndicator, ClassLevel, Subject, TermConfig

    subject = getattr(Subject, subject_enum)
    config = TermConfig(
        scheme_of_work_id="s", academic_year="2026/2027", term="First Term",
        class_level=ClassLevel.BASIC_7, subject=subject,
        term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
        lessons_per_week=2, lesson_duration_minutes=60,
        teaching_days=[0, 2], holidays=[],
    )
    alloc = AllocatedIndicator(
        indicator_code=code,
        # The real published schemes are code-only in the indicator column.
        indicator_description=code,
        content_standard_code=content_standard,
        content_standard_description=content_standard,
        strand="Strand 1", sub_strand="Sub-strand 1", week_number=1,
        source_resources=[], lesson_date=date(2026, 9, 7),
        period_index=1, allocated=True, teaching_week=1,
    )
    return build_lesson(alloc, config, "s")


def _lesson_signature(lp) -> str:
    parts = [
        lp.lesson_topic,
        lp.learning_objectives[0].description,
        lp.starter_activity or "",
        " | ".join(
            (m.description if hasattr(m, "description") else str(m))
            for m in (lp.main_activities or [])
        ),
        lp.assessment or "",
        getattr(lp, "class_assignment", "") or "",
        getattr(lp, "home_assignment", "") or "",
    ]
    return "\n".join(parts)


class TestSubjectIndicatorRegressionContent:
    """Every priority subject plans a real, indicator-specific lesson."""

    @pytest.mark.parametrize(
        "subject_enum,scheme_subject,code,content_standard", _SUBJECT_CASES)
    def test_each_subject_gets_curriculum_grounded_content(
            self, subject_enum, scheme_subject, code, content_standard):
        from src.curriculum.exemplars import lookup_indicator

        subject_label = subject_enum
        record = lookup_indicator(code, scheme_subject)
        assert record is not None, f"no corpus record for {subject_label} {code}"
        lp = _subject_lesson(subject_enum, code, content_standard)
        blob = _lesson_signature(lp)

        # The lesson is about THIS indicator, not the strand name.
        topic_words = set(record.learning_focus.lower().split())
        assert topic_words & set(lp.lesson_topic.lower().split()), (
            f"{subject_label}: topic {lp.lesson_topic!r} ignores the indicator "
            f"focus {record.learning_focus!r}")

        # PHASE 5 — the banned generic filler must not appear.
        for filler in (
            "this lesson builds on",
            "work with your partner",
            "watch and listen carefully",
            "complete the task",
            "learners practise the concept",
        ):
            assert filler not in blob.lower(), (
                f"{subject_label}: generic filler {filler!r}")

        # Every phase answers teacher action / learner action / evidence.
        assert lp.starter_activity and len(lp.starter_activity.split()) >= 12, (
            f"{subject_label}: starter is not concrete")
        assert len(lp.main_activities) >= 2, f"{subject_label}: thin main phase"
        for activity in lp.main_activities:
            text = activity.description if hasattr(activity, "description") else str(activity)
            assert len(text.split()) >= 12, (
                f"{subject_label}: activity too thin: {text!r}")
        assert getattr(lp, "class_assignment", None), (
            f"{subject_label}: no class assignment")
        assert getattr(lp, "home_assignment", None), (
            f"{subject_label}: no home assignment")

        # No debug / internal text anywhere in the lesson.
        low = blob.lower()
        for marker in ("acceptance", "svg", "debug", "fixture", "lorem", "todo"):
            assert marker not in low, f"{subject_label}: internal marker {marker!r}"

    def test_the_subjects_do_not_share_one_generic_lesson(self):
        signatures = {}
        for subject_enum, _scheme_subject, code, cs in _SUBJECT_CASES:
            signatures[subject_enum] = _lesson_signature(
                _subject_lesson(subject_enum, code, cs))
        # Every subject must be distinguishable from every other one.
        for a, sa in signatures.items():
            for b, sb in signatures.items():
                if a == b:
                    continue
                assert sa != sb, f"{a} and {b} generated the identical lesson"

    def test_assignments_are_aligned_with_the_indicator_not_generic(self):
        for subject_enum, _scheme_subject, code, cs in _SUBJECT_CASES:
            subject_label = subject_enum
            lp = _subject_lesson(subject_enum, code, cs)
            home = (getattr(lp, "home_assignment", "") or "").lower()
            class_task = (getattr(lp, "class_assignment", "") or "").lower()
            # The old behaviour forced every indicator into one written question.
            assert class_task.strip(), subject_label
            assert home.strip(), subject_label
            assert "write a short essay about the lesson" not in home, subject_label

    def test_a_corpus_record_never_overrides_a_schemes_own_indicator_wording(self):
        """Schools renumber: the same code can mean something else entirely.

        The official B7.1.1.1.1 is place value up to a billion. A scheme whose
        B7.1.1.1.1 says "Add whole numbers up to 1000" must teach ADDITION — the
        corpus may not inject the official indicator's activities.
        """
        from src.curriculum.lesson_builder import build_lesson
        from src.models import AllocatedIndicator, ClassLevel, Subject, TermConfig

        config = TermConfig(
            scheme_of_work_id="s", academic_year="2026/2027", term="First Term",
            class_level=ClassLevel.BASIC_7, subject=Subject.MATHEMATICS,
            term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
            lessons_per_week=3, lesson_duration_minutes=60,
            teaching_days=[0, 1, 2], holidays=[],
        )
        alloc = AllocatedIndicator(
            indicator_code="B7.1.1.1.1",
            indicator_description="B7.1.1.1.1 Add whole numbers up to 1000",
            content_standard_code="B7.1.1.1",
            content_standard_description="B7.1.1.1 Whole numbers",
            strand="Number", sub_strand="Whole Numbers", week_number=1,
            source_resources=[], lesson_date=date(2026, 9, 7),
            period_index=1, allocated=True, teaching_week=1,
        )
        lp = build_lesson(alloc, config, "s")
        text = " ".join(
            (a.description if hasattr(a, "description") else str(a))
            for a in lp.main_activities).lower()
        assert "billion" not in text, "the official indicator's activities leaked in"
        assert "multi-base" not in text
        assert "whole numbers" in lp.learning_objectives[0].description.lower()

    def test_a_bare_content_standard_code_attaches_no_indicator_evidence(self):
        """B7.1.1.1 is the first standard of Strand 1 in EVERY subject.

        A scheme printing only that standard, with an indicator the corpus does
        not cover, must fall back to the subject pedagogy — never receive
        another indicator's exemplar activities.
        """
        from src.curriculum.lesson_builder import build_lesson
        from src.models import AllocatedIndicator, ClassLevel, Subject, TermConfig

        config = TermConfig(
            scheme_of_work_id="s", academic_year="2026/2027", term="First Term",
            class_level=ClassLevel.BASIC_7, subject=Subject.SOCIAL_STUDIES,
            term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
            lessons_per_week=3, lesson_duration_minutes=60,
            teaching_days=[0, 1, 2], holidays=[],
        )
        alloc = AllocatedIndicator(
            indicator_code="B7.4.1.1.1",
            indicator_description="B7.4.1.1.1 Discuss the roles of members of the family",
            content_standard_code="B7.1.1.1",
            content_standard_description="B7.1.1.1 Standard",
            strand="Our Nation", sub_strand="Family", week_number=1,
            source_resources=[], lesson_date=date(2026, 9, 7),
            period_index=1, allocated=True, teaching_week=1,
        )
        lp = build_lesson(alloc, config, "s")
        blob = (lp.starter_activity + " " + " ".join(
            (a.description if hasattr(a, "description") else str(a))
            for a in lp.main_activities)).lower()
        assert "sanitation" not in blob, "another indicator's evidence was attached"
        assert "family" in blob, "the source's own topic was lost"

    def test_a_scheme_that_prints_its_own_indicator_prose_keeps_authority(self):
        from src.curriculum.lesson_builder import build_lesson
        from src.models import AllocatedIndicator, ClassLevel, Subject, TermConfig

        prose = "B7.1.1.1.2 Distinguish manual and automatic devices in the school ICT laboratory"
        config = TermConfig(
            scheme_of_work_id="s", academic_year="2026/2027", term="First Term",
            class_level=ClassLevel.BASIC_7, subject=Subject.ICT,
            term_start_date=date(2026, 9, 7), term_end_date=date(2026, 12, 18),
            lessons_per_week=2, lesson_duration_minutes=60,
            teaching_days=[0, 2], holidays=[],
        )
        alloc = AllocatedIndicator(
            indicator_code="B7.1.1.1.2", indicator_description=prose,
            content_standard_code="B7.1.1.1",
            content_standard_description="B7.1.1.1 Examine the parts of a computer",
            strand="Introduction to Computing",
            sub_strand="Components of Computers and Computer Systems",
            week_number=1, source_resources=["Keyboard"],
            lesson_date=date(2026, 9, 7), period_index=1, allocated=True,
            teaching_week=1,
        )
        lp = build_lesson(alloc, config, "ICT")
        objective = lp.learning_objectives[0].description.lower()
        assert "distinguish manual and automatic devices" in objective
        # The corpus supplies the pedagogy; the teacher's wording stays.
        assert len(lp.main_activities) >= 2


# ── The canonical code shapes every consumer must recognise ─────────────────

#: (shape, a code in that shape) exactly as the official documents print them.
_CODE_SHAPES = [
    ("Computing / Mathematics / PHE", "B7.1.1.1.1"),
    ("bare, no level letter", "1.1.1.1"),
    ("English Language", "B7/JHS1.1.1.1.1"),
    ("RME / Social Studies / Creative Arts", "B7/JHS1 1.1.1.1"),
    ("KG range", "K2.1.1.1.1-3"),
]


class TestCanonicalCodeShapes:
    """A scheme that prints "B7/JHS1 1.1.1.1" must not be read as PROSE.

    The real defect: only the dotted shape was recognised, so the codes that
    English/RME/Social Studies/Creative Arts schemes print reached the lesson
    as learner-facing text ("Learners can B7/JHS1 1.1.1.1") and the template
    printed the code twice ("B7.1.1.1 B7/JHS1 1.1.1.1 ...").
    """

    @pytest.mark.parametrize("shape,code", _CODE_SHAPES)
    def test_a_code_only_cell_is_recognised_in_every_shape(self, shape, code):
        from src.curriculum.lesson_builder import _is_code_only

        assert _is_code_only(code), f"{shape}: {code!r} not seen as a code"

    @pytest.mark.parametrize("shape,code", _CODE_SHAPES)
    def test_the_parser_rejoin_of_a_kg_range_is_still_code_only(self, shape, code):
        from src.curriculum.lesson_builder import _is_code_only

        if code.startswith("K"):
            assert _is_code_only(f"{code} {code}")

    @pytest.mark.parametrize("shape,code", _CODE_SHAPES)
    def test_the_code_is_stripped_from_real_prose(self, shape, code):
        from src.curriculum.lesson_builder import strip_indicator_code

        prose = "Examine ways of dealing with sanitation challenges"
        assert strip_indicator_code(f"{code} {prose}") == prose, shape
        assert strip_indicator_code(f"{code}. {prose}") == prose, shape

    @pytest.mark.parametrize("shape,code", _CODE_SHAPES)
    def test_real_prose_is_never_mistaken_for_a_code(self, shape, code):
        from src.curriculum.lesson_builder import _is_code_only

        prose = "B7.1.1.1.2 Distinguish manual and automatic devices"
        assert not _is_code_only(prose)
        assert not _is_code_only("Discuss the types of environment")
        assert not _is_code_only("Explain the 3 states of matter")

    @pytest.mark.parametrize("shape,code", _CODE_SHAPES)
    def test_the_template_never_prints_a_code_twice(self, shape, code):
        from src.engines.official_ges_template import _code_and_text

        # The stored text already carries its own code — the approved cell
        # format prints the code exactly once.
        text = f"{code} Examine ways of dealing with sanitation challenges"
        assert _code_and_text(code, text) == text, shape

    @pytest.mark.parametrize("shape,code", _CODE_SHAPES)
    def test_the_template_still_pairs_a_code_with_its_description(self, shape, code):
        from src.engines.official_ges_template import _code_and_text

        assert _code_and_text(code, "Examine the environment") == (
            f"{code} Examine the environment"), shape

    def test_a_space_form_code_normalizes_for_corpus_lookup(self):
        """RME prints the code with a SPACE, English with a DOT.

        Both are the same indicator (level + 1.1.1.1) and must answer for the
        same curriculum evidence, whatever shape the teacher's upload used.
        """
        from src.curriculum import CODE_PREFIX_RE
        from src.curriculum.exemplars import lookup_indicator, normalize_code

        raw = "B7/JHS1 1.1.1.1 Examine ways of dealing with sanitation challenges"
        stripped = CODE_PREFIX_RE.sub("", raw).strip()
        assert stripped == "Examine ways of dealing with sanitation challenges"
        space_form = normalize_code("B7/JHS1 1.1.1.1")
        dot_form = normalize_code("B7/JHS1.1.1.1.1")
        assert space_form == dot_form == "B7.1.1.1.1"
        # Either shape resolves to the Social Studies record.
        assert lookup_indicator("B7/JHS1 1.1.1.1", "Social Studies") is not None
        assert lookup_indicator("B7/JHS1.1.1.1.1", "Social Studies") is not None


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
