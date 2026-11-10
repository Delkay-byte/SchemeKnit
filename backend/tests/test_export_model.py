"""Export model tests: the browser receives data, never a built file."""

import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.engines.export_model import build_docx_model
from src.engines.official_ges_levels import spec_for_template_id
from src.routers import generation as gen_router
from tests.conftest import make_user
from tests.test_export_download import make_job_with_lessons

JHS_TEMPLATE_ID = "tpl-official-ges-nacca-jhs"
SECTION_TEMPLATE_ID = "tpl-jhs-ges"


@pytest.mark.asyncio
async def test_jhs_model_is_a_render_model_not_a_document(db):
    user = make_user(db)
    _scheme, job = make_job_with_lessons(db, user, lessons=2)

    model = await gen_router.get_export_model(
        job.id, "docx", "GES-style", JHS_TEMPLATE_ID, user, db)

    assert model["schema_version"] == 1
    assert model["renderer"] == "form"
    assert model["lesson_count"] == 2
    assert len(model["documents"]) == 2
    assert "PK" not in str(model)[:2]

    form = model["documents"][0]["form"]
    assert form["kind"] == "official_ges"
    assert form["asset"].startswith("docx-templates/")
    assert spec_for_template_id(JHS_TEMPLATE_ID).filename in form["asset"]
    # Server-resolved content travels as text, not as an OOXML document.
    assert form["tokens"]["INSERT_WEEK_ENDING"]
    assert isinstance(form["grid_fills"], list)
    assert form["standalone_header_lines"]
    # The additive assessment structure is server-authored (empty here: the
    # fixture lessons have no DoK items, rubric or assignments).
    assert "appendices" in model
    assert model["appendices"][0] == []


@pytest.mark.asyncio
async def test_section_template_returns_neutral_blocks(db):
    user = make_user(db)
    _scheme, job = make_job_with_lessons(db, user, lessons=1)

    model = await gen_router.get_export_model(
        job.id, "docx", "GES-style", SECTION_TEMPLATE_ID, user, db)

    assert model["renderer"] == "blocks"
    blocks = model["documents"][0]["blocks"]
    kinds = {block["kind"] for block in blocks}
    assert {"heading", "paragraph", "pageBreak"} <= kinds
    headings = [block["text"] for block in blocks
                if block["kind"] == "heading"]
    assert "LESSON PLAN" in headings
    assert "Assessment" in headings


@pytest.mark.asyncio
async def test_zip_model_requires_the_zip_entitlement(db):
    user = make_user(db)
    _scheme, job = make_job_with_lessons(db, user, lessons=1)

    with pytest.raises(HTTPException) as error:
        await gen_router.get_export_model(
            job.id, "zip", "GES-style", JHS_TEMPLATE_ID, user, db)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_model_is_owner_scoped(db):
    owner = make_user(db, email="owner@example.com")
    other = make_user(db, email="other@example.com")
    _scheme, job = make_job_with_lessons(db, owner, lessons=1)

    with pytest.raises(HTTPException) as error:
        await gen_router.get_export_model(
            job.id, "docx", "GES-style", JHS_TEMPLATE_ID, other, db)
    assert error.value.status_code == 404


def test_custom_structure_model_keeps_merges():
    from datetime import date

    from src.models import ClassLevel, LessonPlan, Subject

    lesson = LessonPlan(
        scheme_of_work_id="s", term_config_id="j", week_number=1,
        lesson_sequence=1, lesson_date=date(2026, 2, 3),
        class_level=ClassLevel.BASIC_7, subject=Subject.SCIENCE,
        duration_minutes=60,
    )
    structure = {
        "tables": [{
            "rows": 2, "cols": 3,
            "cells": [
                {"r": 0, "c": 0, "label": "School", "field": "school_name",
                 "colspan": 2},
                {"r": 0, "c": 1, "covered": True},
                {"r": 0, "c": 2, "label": "Week", "field": "week_number"},
                {"r": 1, "c": 0, "role": "activity_content",
                 "row_phase_kind": "main"},
            ],
        }],
    }

    model = build_docx_model([lesson], structure=structure,
                             render_context={"term": "Term 1"})
    assert model["renderer"] == "blocks"
    table = next(block for block in model["documents"][0]["blocks"]
                 if block["kind"] == "customTable")
    assert table["rows"] == 2
    assert table["cols"] == 3
    assert any(cell.get("colspan") == 2 for cell in table["cells"])
    assert all(not cell.get("covered") for cell in table["cells"])
