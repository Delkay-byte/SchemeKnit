"""
Approved organizational template tests: structure, schema, normalization,
rendering, enrichment merge rules.
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.engines.approved_template import (
    TEMPLATE_ID, TEMPLATE_NAME, build_approved_structure,
    validate_approved_lesson_json, normalize_lesson_to_approved,
    APPROVED_SYSTEM_PROMPT,
)
from src.engines.docx_export import render_custom_template
from src.models import LessonPlan
from docx import Document


def make_lesson(**overrides):
    base = dict(
        scheme_of_work_id="scheme-1", term_config_id="job-1",
        week_number=1, lesson_sequence=1, lesson_date=date(2026, 9, 11),
        lesson_number=1, school_name="S", teacher_name="T",
        subject="Science", class_level="Basic 9", class_size=24,
        duration_minutes=60, strand="Diversity of Matter", sub_strand="Materials",
        content_standard="B9.1.1.1 Show understanding",
        indicators=["B9.1.1.1.1 Identify"],
        lesson_topic="Binary Compounds", introduction="Starter.",
        main_activities=[{"phase": "MAIN", "description": "Present."}],
        learner_activities=[{"phase": "LEARNER", "description": "Discuss."}],
        assessment="Assess.", conclusion="Conclude.",
        references=["Curr Pg. 33"], core_competencies=["CC"],
    )
    base.update(overrides)
    return LessonPlan(**base)


class TestApprovedStructure:
    """The golden master is DERIVED from the approved source document, so these
    numbers are the file's measured topology, not a transcription.
    """

    def test_topology(self):
        s = build_approved_structure()
        assert len(s["tables"]) == 4
        assert [(t["rows"], t["cols"]) for t in s["tables"]] == [
            (4, 4), (4, 2), (4, 2), (4, 3)]

    def test_source_document_declared(self):
        s = build_approved_structure()
        assert s["meta"]["approved_source"].endswith(
            "ges_jhs_lesson_plan_template.docx")

    def test_key_labels_mapped(self):
        s = build_approved_structure()
        by_label = {m["label"]: m for m in s["mappings"]}
        # Field coordinates are pinned to the source's own bracketed tokens.
        assert by_label["SUBJECT"]["field"] == "subject"
        assert by_label["CONTENT STANDARD"]["field"] == "content_standard"
        assert by_label["INDICATOR"]["field"] == "indicators"
        assert by_label["REFERENCE"]["field"] == "references"
        assert by_label["STRAND"]["field"] == "strand"
        assert by_label["SUB-STRAND"]["field"] == "sub_strand"
        assert by_label["KEYWORDS / VOCABULARY"]["field"] == "keywords"
        assert by_label["TEACHING & LEARNING RESOURCES (TLRs)"]["field"] == \
            "teaching_learning_resources"
        # "period" is a context-only field (no stored lesson column): it
        # resolves from the caller's context or renders blank, never invented.
        assert by_label["PERIOD"]["field"] == "period"

    def test_activity_grid_roles(self):
        s = build_approved_structure()
        grids = [t["activity_grid"] for t in s["tables"] if t.get("activity_grid")]
        assert len(grids) == 1
        assert grids[0]["phase_cols"] == [0]
        assert grids[0]["activity_cols"] == [1]
        assert grids[0]["resource_cols"] == [2]

    def test_phase_names_match_source(self):
        from src.engines.approved_template import APPROVED_PHASE_NAMES
        assert APPROVED_PHASE_NAMES == (
            "PHASE 1: STARTER / INTRO",
            "PHASE 2: MAIN LEARNING",
            "PHASE 3: PLENARY / REFLECTION")

    def test_template_id_stable(self):
        assert TEMPLATE_ID == "tpl-approved-org-headteacher"
        assert "Headteacher" in TEMPLATE_NAME


class TestApprovedSchema:
    def test_valid_payload(self):
        ok, norm = validate_approved_lesson_json({
            "lesson_topic": "T",
            "phases": [{"name": "PHASE 1: STARTER", "learner_activities": ["Do X"]}],
            "assessment": ["Q1?"],
        })
        assert ok is True
        assert norm["phases"][0]["learner_activities"] == ["Do X"]

    def test_unknown_keys_dropped_not_fatal(self):
        ok, norm = validate_approved_lesson_json({
            "strand": "INVENTED", "phases": [], "bogus_field": 1,
        })
        assert ok is True
        assert "strand" not in norm and "bogus_field" not in norm

    def test_non_object_rejected(self):
        ok, errors = validate_approved_lesson_json("just text")
        assert ok is False and errors

    def test_dict_items_coerced(self):
        ok, norm = validate_approved_lesson_json({
            "assessment": [{"type": "quiz"}, "Answer orally."],
        })
        assert ok is True
        assert any("Answer orally" in a for a in norm["assessment"])

    def test_system_prompt_rules(self):
        assert "NEVER invent curriculum facts" in APPROVED_SYSTEM_PROMPT
        assert "markdown fences" in APPROVED_SYSTEM_PROMPT
        assert "GES" not in APPROVED_SYSTEM_PROMPT and "NaCCA" not in APPROVED_SYSTEM_PROMPT


class TestNormalize:
    def test_deterministic_no_ai(self):
        norm = normalize_lesson_to_approved(make_lesson())
        assert norm["phases"][0]["learner_activities"] == ["Starter."]
        assert "Present." in norm["phases"][1]["teacher_activities"]
        assert norm["assessment"] == ["Assess."]
        assert norm["reflection"] == "Conclude."
        assert "strand" not in norm and "subject" not in norm  # curriculum excluded

    def test_missing_optional_blank(self):
        lp = make_lesson(introduction="", assessment="", conclusion="")
        norm = normalize_lesson_to_approved(lp)
        assert norm["phases"][0]["learner_activities"] == []
        assert norm["assessment"] == []
        assert norm["reflection"] == ""


class TestApprovedRender:
    """Rendering the approved template must reproduce the SOURCE document's
    topology, not merely agree with its own IR.
    """

    def _render(self, tmp_path, lesson=None, template_id="tpl-approved-org-headteacher"):
        from src.engines.docx_export import DOCXExportEngine
        from src.engines.template_engine import get_template_by_id
        out = tmp_path / "approved.docx"
        engine = DOCXExportEngine()
        engine.export_single(lesson or make_lesson(),
                             get_template_by_id(template_id), out)
        return out

    def test_render_matches_approved_source_topology(self, tmp_path):
        from src.validators.docx_structure_compare import validate_generated
        out = self._render(tmp_path)
        rep = validate_generated(
            out,
            expected_values=["Diversity of Matter", "B9.1.1.1.1", "Starter.",
                             "Present.", "Assess."],
            forbidden_values=["Forces & Energy", "B7.4.3.1"])
        assert rep["pass"], [
            (g, c["name"], c["detail"])
            for g in ("structure", "content")
            for c in rep[g]["checks"] if not c["pass"]]

    def test_render_is_same_path_for_both_approved_ids(self, tmp_path):
        """The headteacher id and the verified JHS form id name the same source
        document, so both must render identical topology.
        """
        from src.validators.docx_structure_compare import compare_structure, \
            golden_master_source_path
        a = self._render(tmp_path, template_id="tpl-approved-org-headteacher")
        b = self._render(tmp_path, template_id="tpl-official-ges-nacca-jhs")
        source = golden_master_source_path()
        assert compare_structure(source, a)["pass"]
        assert compare_structure(source, b)["pass"]

    def test_no_guidance_or_tokens_leak(self, tmp_path):
        from src.validators.docx_structure_compare import compare_content
        out = self._render(tmp_path)
        rep = compare_content(out)
        assert rep["pass"], [c for c in rep["checks"] if not c["pass"]]

    def test_multi_lesson_document_blocks_match_source(self, tmp_path):
        from src.validators.docx_structure_compare import compare_structure, \
            golden_master_source_path
        from src.engines.docx_export import DOCXExportEngine
        from src.engines.template_engine import get_template_by_id
        out = tmp_path / "multi.docx"
        engine = DOCXExportEngine()
        engine.export_combined([make_lesson(), make_lesson(lesson_sequence=2)],
                               get_template_by_id("tpl-approved-org-headteacher"), out)
        rep = compare_structure(golden_master_source_path(), out)
        assert rep["pass"], [c for c in rep["checks"] if not c["pass"]]
        assert rep["lessons"] == 2


class TestEnrichMerge:
    @pytest.mark.asyncio
    async def test_enrich_appends_without_destroying(self, db):
        from tests.conftest import make_entitled_teacher
        from src.routers import ai_regeneration as air
        from src.database import SchemeDB, LessonPlanDB, GenerationJobDB, generate_id
        from unittest.mock import MagicMock
        u, _school, _lic = make_entitled_teacher(db, email="enrich@t.test")
        scheme = SchemeDB(id=generate_id(), owner_id=u.id, filename="s.docx",
                          subject="Science", class_level="Basic 9")
        db.add(scheme)
        db.commit()
        job = GenerationJobDB(id=generate_id(), owner_id=u.id, scheme_id=scheme.id,
                              status="completed")
        db.add(job)
        db.flush()
        lp = LessonPlanDB(id=generate_id(), job_id=job.id, owner_id=u.id,
                          scheme_id=scheme.id, week_number=1, lesson_sequence=1,
                          class_level="Basic 9", subject="Science",
                          introduction="Keep me.", assessment="Keep this too.")
        db.add(lp)
        db.commit()
        provider = MagicMock()
        provider.get_name.return_value = "ollama"
        provider.model = "test"
        provider.generate_structured.return_value = {
            "lesson_topic": "HACK ATTEMPT (must be ignored)",
            "strand": "INVENTED CURRICULUM (must be ignored)",
            "phases": [{"name": "PHASE 1: STARTER",
                        "learner_activities": ["AI starter line."]}],
            "assessment": ["AI assessment line."],
            "new_words": ["Atom"],
        }
        with __import__("unittest.mock", fromlist=["patch"]).patch.object(
                air, "get_provider", return_value=provider):
            res = await air.enrich_lesson(
                air.EnrichLessonRequest(lesson_plan_id=lp.id, ai_mode="ollama"),
                u, db)
        assert "learner:PHASE 1: STARTER" in res["written"]
        db.refresh(lp)
        import json
        assert "Keep me." in (lp.introduction or "")  # deterministic kept
        assert "AI starter line." in json.dumps(lp.learner_activities)
        assert "AI assessment line." in (lp.assessment or "")
        assert "Atom" in json.dumps(lp.keywords)
        # curriculum/model fields never written by AI
        assert lp.lesson_topic != "HACK ATTEMPT (must be ignored)"
        assert lp.strand != "INVENTED CURRICULUM (must be ignored)"
