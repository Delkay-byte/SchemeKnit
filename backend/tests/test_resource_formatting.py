"""Resource-list normalization contracts.

Generated resources are complete descriptions. Commas inside one material
description must survive; only real list structure, newlines and semicolons
separate items. The same normalized list is used by the API and by exports.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from src.ai_resource_text import (  # noqa: E402
    normalize_exact_items, normalize_resource_items,
)
from src.database import LessonPlanDB  # noqa: E402
from src.routers.generation import _db_to_lesson_model, _serialize_lesson  # noqa: E402
from tests.conftest import make_user  # noqa: E402
from tests.test_export_download import make_job_with_lessons  # noqa: E402

COMMA_ITEM = (
    "Samples of table salt, water, and baking soda "
    "(for observation only)")


def test_comma_inside_one_description_is_preserved():
    assert normalize_resource_items([COMMA_ITEM]) == [COMMA_ITEM]


def test_semicolons_and_newlines_separate_real_items():
    assert normalize_resource_items(
        "Chart; Chalkboard\nExercise books") == [
            "Chart", "Chalkboard", "Exercise books"]


def test_duplicates_are_removed_case_insensitively_and_whitespace_cleaned():
    assert normalize_resource_items([
        "  Chart  ", "chart", "CHALKBOARD", "Chalkboard", "",
    ]) == ["Chart", "CHALKBOARD"]


def test_placeholder_and_empty_entries_are_dropped():
    assert normalize_resource_items(
        [None, "", "  ", "None", "N/A", "Chart"]) == ["Chart"]


def test_serialized_list_is_parsed_without_comma_splitting():
    assert normalize_resource_items(
        '["Samples of table salt, water and chalk", "Chart"]') == [
            "Samples of table salt, water and chalk", "Chart"]


def test_indicator_punctuation_is_preserved_exactly():
    indicator = (
        "B6.2.2.1.1 : Read words with ending sounds like 'sure' as in "
        "measure; 'ture' as in creature and 'tch' as in stretch")
    assert normalize_exact_items([indicator]) == [indicator]


def test_api_and_model_conversion_keep_the_same_complete_resource(db):
    user = make_user(db)
    scheme, _job = make_job_with_lessons(db, user, lessons=1)
    row = db.query(LessonPlanDB).one()
    row.teaching_learning_resources = [COMMA_ITEM, "Chart", "chart"]
    db.commit()

    model = _db_to_lesson_model(row)
    assert model.teaching_learning_resources == [COMMA_ITEM, "Chart"]

    serialized = _serialize_lesson(row, scheme)
    assert serialized["teaching_learning_resources"] == [COMMA_ITEM, "Chart"]
