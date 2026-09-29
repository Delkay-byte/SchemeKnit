"""
Layer 1 — Curriculum Evidence Provider tests.

Contract under test (RAG-ready, provenance mandatory, empty state valid):
  * exact indicator-code lookup outranks keyword matches
  * subject filtering happens before generation (B7.1.1.1.1 exists in several
    subjects — the wrong subject is never returned)
  * provenance is mandatory on every retrieved record
  * empty retrieval is a valid state (None / [] never crashes a caller)
  * the interface is stable: a future hybrid/vector provider plugs in through
    the same protocol without touching the lesson engine
"""

from __future__ import annotations

import pytest

from src.curriculum.evidence import (
    CurriculumEvidence,
    CurriculumEvidenceProvider,
    EvidenceProvenance,
    EvidenceRequest,
    StructuredExemplarProvider,
    evidence_for_lesson,
    get_evidence_provider,
    register_evidence_provider,
    request_from_lesson,
    set_default_evidence_provider,
)


# ── Provenance ─────────────────────────────────────────────────────────────


def test_provenance_defaults_mark_evidence_as_official():
    prov = EvidenceProvenance(source_name="NaCCA exemplar corpus")
    assert prov.source_type == "official"
    assert prov.subject == ""


def test_provenance_is_mandatory_on_retrieved_records():
    from src.curriculum.exemplars import lookup_indicator

    rec = lookup_indicator("B7.1.1.1.1", "Mathematics")
    if rec is None:
        pytest.skip("corpus has no B7.1.1.1.1 Mathematics record")
    ev = StructuredExemplarProvider().retrieve_exact(
        EvidenceRequest(subject="Mathematics", indicator_code="B7.1.1.1.1"))
    assert ev is not None
    assert ev.provenance.source_name
    assert ev.provenance.location


# ── Provider protocol ──────────────────────────────────────────────────────


def test_structured_exemplar_provider_implements_protocol():
    provider = StructuredExemplarProvider()
    assert isinstance(provider, CurriculumEvidenceProvider)


def test_exact_lookup_returns_record_with_verbs():
    from src.curriculum.exemplars import lookup_indicator

    rec = lookup_indicator("B7.1.1.1.1", "Mathematics")
    if rec is None:
        pytest.skip("corpus has no B7.1.1.1.1 Mathematics record")
    ev = StructuredExemplarProvider().retrieve_exact(
        EvidenceRequest(subject="Mathematics", indicator_code="B7.1.1.1.1"))
    assert isinstance(ev, CurriculumEvidence)
    assert ev.match_type == "exact"
    assert ev.provenance.subject
    assert ev.curriculum_action_verbs


def test_wrong_subject_returns_none():
    """B7.1.1.1.1 exists in several subjects; another subject is never served."""
    ev = StructuredExemplarProvider().retrieve_exact(
        EvidenceRequest(subject="Religious and Moral Education",
                        indicator_code="B7.1.1.1.1"))
    # The corpus may genuinely have an RME record with this code — that is
    # correct behaviour. The invariant that matters: the returned record's
    # subject is RME, never silently Mathematics.
    if ev is not None:
        assert "Religious" in ev.provenance.subject or "RME" in ev.provenance.subject


def test_missing_code_returns_none_without_raising():
    ev = StructuredExemplarProvider().retrieve_exact(
        EvidenceRequest(subject="Mathematics", indicator_code="ZZ9.9.9.9.9"))
    assert ev is None


def test_keyword_retrieval_requires_subject():
    """Keyword retrieval without a subject is refused: it cannot filter."""
    results = StructuredExemplarProvider().retrieve_keyword(
        EvidenceRequest(terms=["place", "value"]))
    assert results == []


def test_keyword_retrieval_can_find_real_content():
    results = StructuredExemplarProvider().retrieve_keyword(
        EvidenceRequest(subject="Mathematics", terms=["place", "value"]))
    if not results:
        pytest.skip("corpus has no place-value Mathematics record")
    assert all(r.match_type == "keyword" for r in results)
    assert all(r.provenance.subject for r in results)


def test_empty_retrieval_is_valid_state():
    """No evidence must never crash; the pedagogy layer carries the lesson."""
    ev = evidence_for_lesson(
        EvidenceRequest(subject="Mathematics",
                        indicator_code="ZZ9.9.9.9.9"))
    assert ev is None


# ── Registry (RAG-ready plug-in point) ─────────────────────────────────────


class _RecordingProvider:
    """Minimal stub proving a future hybrid/vector provider plugs in here."""

    def __init__(self) -> None:
        self.calls = 0

    def retrieve_exact(self, request: EvidenceRequest):
        self.calls += 1
        return None

    def retrieve_content_standard(self, request: EvidenceRequest):
        self.calls += 1
        return None

    def retrieve_keyword(self, request: EvidenceRequest):
        self.calls += 1
        return None

    def name(self) -> str:
        return "test-recording-provider"


def test_provider_registration_and_default_swap():
    stub = _RecordingProvider()
    register_evidence_provider(stub)
    previous = StructuredExemplarProvider()
    set_default_evidence_provider(stub)
    try:
        assert get_evidence_provider() is stub
        result = evidence_for_lesson(EvidenceRequest(subject="Mathematics",
                                                     indicator_code="B7.1.1.1.1"))
        assert result is None  # stub retrieves nothing — a valid empty state
        assert stub.calls >= 1
    finally:
        # Restore the corpus-backed default so other tests are unaffected.
        set_default_evidence_provider(previous)


def test_default_provider_is_corpus_backed():
    assert isinstance(get_evidence_provider(), StructuredExemplarProvider)


# ── Request building from an allocation ────────────────────────────────────


def test_request_from_lesson_carries_subject_and_code():
    from src.models import AllocatedIndicator

    alloc = AllocatedIndicator(
        indicator_code="B7.1.1.1.1",
        indicator_description="Add whole numbers",
        content_standard_code="B7.1.1.1",
        content_standard_description="Number",
        strand="Number", sub_strand="Whole Numbers",
        week_number=1, period_index=1, allocated=True, teaching_week=1)
    req = request_from_lesson(alloc, subject="Mathematics")
    assert req.subject == "Mathematics"
    assert req.indicator_code == "B7.1.1.1.1"


def test_evidence_record_round_trips_focus_and_verbs():
    ev = CurriculumEvidence(
        provenance=EvidenceProvenance(source_name="t"),
        learning_focus="Place value", curriculum_action_verbs=["model"])
    assert ev.has_patterns is False
    ev2 = CurriculumEvidence(
        provenance=EvidenceProvenance(source_name="t"),
        exemplar_activity_patterns=["Sort items"])
    assert ev2.has_patterns is True
