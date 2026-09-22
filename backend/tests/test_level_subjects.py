"""
Level-aware subject availability tests (§3).

The canonical LEVEL → AVAILABLE SUBJECTS mapping is the single source of truth.
KG subjects must appear for KG levels, SHS subjects for SHS 1-3, and the
existing Basic/JHS coverage must remain intact and not leak across levels.
"""

import asyncio

from src.models import (
    ClassLevel, Subject, subjects_for_class_level,
    subjects_for_educational_level, EducationalLevel,
)


def values(level):
    return [s.value for s in subjects_for_class_level(level)]


class TestKGSubjects:
    def test_kg1_has_kg_subjects(self):
        subjects = values(ClassLevel.KG1)
        assert "Numeracy" in subjects
        assert "Language and Literacy" in subjects
        assert "Our World Our People" in subjects
        assert "Physical Development" in subjects

    def test_kg2_has_kg_subjects(self):
        assert "Numeracy" in values(ClassLevel.KG2)

    def test_nursery_has_kg_subjects(self):
        assert "Language and Literacy" in values(ClassLevel.NURSERY)

    def test_kg_does_not_expose_shs_subjects(self):
        subjects = values(ClassLevel.KG1)
        assert "Core Mathematics" not in subjects
        assert "Biology" not in subjects
        assert "Chemistry" not in subjects
        assert "Physics" not in subjects


class TestSHSSubjects:
    def test_shs1_has_shs_subjects(self):
        subjects = values(ClassLevel.SHS_1)
        assert "Core Mathematics" in subjects
        assert "Integrated Science" in subjects
        assert "Biology" in subjects
        assert "Chemistry" in subjects
        assert "Physics" in subjects
        assert "Elective Mathematics" in subjects

    def test_shs2_has_shs_subjects(self):
        assert "Economics" in values(ClassLevel.SHS_2)

    def test_shs3_has_shs_subjects(self):
        assert "Geography" in values(ClassLevel.SHS_3)

    def test_shs_does_not_expose_kg_subjects(self):
        subjects = values(ClassLevel.SHS_1)
        assert "Numeracy" not in subjects
        assert "Language and Literacy" not in subjects


class TestExistingBasicAndJHSRegression:
    def test_jhs_keeps_existing_coverage(self):
        subjects = values(ClassLevel.BASIC_7)
        assert "English Language" in subjects
        assert "Mathematics" in subjects
        assert "Science" in subjects
        assert "Social Studies" in subjects
        assert "Career Technology" in subjects

    def test_jhs_does_not_expose_shs_only_subjects(self):
        subjects = values(ClassLevel.BASIC_9)
        assert "Core Mathematics" not in subjects
        assert "Biology" not in subjects

    def test_primary_keeps_existing_coverage(self):
        subjects = values(ClassLevel.BASIC_4)
        assert "Mathematics" in subjects
        assert "Science" in subjects
        assert "English Language" in subjects

    def test_educational_level_union(self):
        shs = [s.value for s in subjects_for_educational_level(EducationalLevel.SHS)]
        assert "Core Mathematics" in shs and "Physics" in shs
        ec = values(ClassLevel.KG1)
        assert "Numeracy" in ec

    def test_unknown_level_falls_back_to_all(self):
        from src.models import ALL_SUBJECTS
        subjects = subjects_for_class_level("Not A Level")
        assert len(subjects) == len(ALL_SUBJECTS)
        # The explicit UNKNOWN sentinel is a "needs confirmation" state, not an
        # offered subject, so it is never in the selectable list.
        assert Subject.UNKNOWN not in subjects


class TestSubjectsEndpoint:
    def test_level_scoped_endpoint(self):
        from src.routers.settings import list_subjects

        res = asyncio.run(list_subjects(level="KG 1"))
        assert "Numeracy" in res["subjects"]
        assert "Core Mathematics" not in res["subjects"]

        res = asyncio.run(list_subjects(level="SHS 2"))
        assert "Core Mathematics" in res["subjects"]

    def test_global_endpoint_returns_catalogue(self):
        from src.routers.settings import list_subjects

        res = asyncio.run(list_subjects())
        assert "Numeracy" in res["subjects"]
        assert "Biology" in res["subjects"]

    def test_by_level_endpoint(self):
        from src.routers.settings import list_subjects_by_level

        res = asyncio.run(list_subjects_by_level())
        by_level = {row["class_level"]: row for row in res["levels"]}
        assert "Numeracy" in by_level["KG 1"]["subjects"]
        assert "Core Mathematics" in by_level["SHS 1"]["subjects"]
        assert by_level["KG 1"]["educational_level"] == "Early Childhood"
