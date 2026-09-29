"""
SchemeKnit Curriculum Evidence Layer (Layer 1)
=================================================

Retrieves OFFICIAL curriculum evidence for one lesson BEFORE any pedagogy,
pattern selection or generation happens. This is the "Retrieve" step of the
eventual RAG pipeline:

    Teacher Scheme
      → Curriculum IR
      → CURRICULUM EVIDENCE          ← this module
      → Subject Pedagogy
      → Lesson Pattern Selection
      → Deterministic Lesson

Design rules (from the RAG-ready architecture contract)
-------------------------------------------------------
1.  **Exact indicator-code retrieval outranks vague semantic matches.**
    A lookup by ``B7.1.1.1.2`` in the right subject always beats a fuzzy
    keyword hit, and a keyword hit never silently replaces an exact match.
2.  **Subject and level filtering happen before generation.** Evidence for
    another subject is never returned to a lesson, even when the code matches
    (``B7.1.1.1.1`` exists in Computing, Mathematics and PHE).
3.  **The source week remains authoritative.** Evidence guides pedagogical
    interpretation; it never overwrites the teacher's week, sequence, topic,
    teaching period, source resources or school-specific wording.
4.  **Provenance is mandatory.** Every retrieved item carries ``source_type``,
    ``source_name``, ``subject``, ``level``, ``indicator``, ``version`` and a
    ``location``/reference. An untrusted retrieval result can never silently
    become curriculum authority.
5.  **Empty retrieval is a valid state.** When no official exemplar exists the
    provider returns nothing (``None``/``[]``) and the bounded subject pedagogy
    layer carries the lesson — provenance records the miss honestly.
6.  **No new external dependency.** The current provider is backed purely by
    the existing structured NaCCA exemplar corpus. A future vector/hybrid
    provider can be registered through :func:`register_evidence_provider`
    WITHOUT touching the lesson engine.

The retrieval interface is deliberately small and stable
(:class:`CurriculumEvidenceProvider`) so a future RAG implementation
(structured → keyword → hybrid → semantic/vector) can plug in here and the
lesson engine never changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

# ── Evidence record ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EvidenceProvenance:
    """Where a piece of curriculum evidence came from.

    Provenance is first-class: it lets review, export and the quality gate say
    *why* a lesson was built the way it was, and it stops an untrusted result
    from silently becoming curriculum authority.
    """

    #: ``official`` (NaCCA/curriculum corpus), ``teacher`` (uploaded scheme /
    #: school-approved resource) or ``product`` (approved patterns, tested
    #: activity libraries, teacher-approved corrections).
    source_type: str = "official"
    source_name: str = ""
    subject: str = ""
    level: str = ""
    indicator: str = ""
    version: str = ""
    #: A stable reference back into the source (URL, document section, corpus
    #: record id …). Must be present for ``official`` evidence.
    location: str = ""
    #: Free-text provenance note (how the evidence was derived).
    note: str = ""


@dataclass(frozen=True)
class CurriculumEvidence:
    """One retrieved piece of curriculum evidence for a lesson.

    Carries everything the pedagogy/pattern layers need from the official
    curriculum: the learning focus, the action verbs the official exemplars
    require, exemplar activity patterns, assessment / assignment / resource
    patterns, focus terms and core competencies.
    """

    provenance: EvidenceProvenance
    learning_focus: str = ""
    curriculum_action_verbs: List[str] = field(default_factory=list)
    exemplar_activity_patterns: List[str] = field(default_factory=list)
    assessment_patterns: List[str] = field(default_factory=list)
    assignment_patterns: List[str] = field(default_factory=list)
    class_assignment_pattern: str = ""
    home_assignment_pattern: str = ""
    suitable_resource_patterns: List[str] = field(default_factory=list)
    focus_terms: List[str] = field(default_factory=list)
    core_competencies: List[str] = field(default_factory=list)
    strand: str = ""
    sub_strand: str = ""
    content_standard_code: str = ""
    indicator_code: str = ""
    #: How strongly this evidence matches the request. ``"exact"`` =
    #: structured exact-code lookup; ``"standard"`` = matched via the content
    #: standard; ``"keyword"`` = keyword/hybrid match. Exact always outranks
    #: keyword — see :class:`CurriculumEvidenceProvider`.
    match_type: str = "exact"

    @property
    def has_patterns(self) -> bool:
        """True when this record carries usable activity evidence."""
        return bool(
            self.exemplar_activity_patterns
            or self.assessment_patterns
            or self.class_assignment_pattern
            or self.home_assignment_pattern
        )


# ── Retrieval request ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EvidenceRequest:
    """What a lesson needs from the curriculum evidence layer.

    ``subject``/``level``/``indicator_code`` drive the structured lookup;
    ``terms`` (the indicator's own focus words) drive keyword/hybrid search;
    ``content_standard_code`` enables the bounded content-standard fallback.
    Any field may be blank — an empty request is valid and retrieves nothing.
    """

    subject: str = ""
    level: str = ""
    indicator_code: str = ""
    content_standard_code: str = ""
    terms: List[str] = field(default_factory=list)
    #: The week the teacher's scheme assigned. NEVER used to filter evidence
    #: away (the official corpus may be organised differently); recorded so
    #: retrieval results and provenance can note the source-week relationship.
    source_week: Optional[int] = None


# ── Provider interface ───────────────────────────────────────────────────────


@runtime_checkable
class CurriculumEvidenceProvider(Protocol):
    """Stable retrieval contract for the curriculum evidence layer.

    A future RAG implementation (keyword → hybrid → semantic/vector) implements
    this interface and is registered via
    :func:`register_evidence_provider`; the lesson engine, pattern selection
    and quality gate never change.

    Implementations MUST honour the layer contract:

    * exact indicator-code lookup outranks vague semantic matches;
    * subject and level filtering happen BEFORE anything is returned;
    * every returned :class:`CurriculumEvidence` carries provenance;
    * empty retrieval is a valid state (``None`` / ``[]``), and a low
      confidence match must never become curriculum authority.
    """

    def retrieve_exact(self, request: EvidenceRequest) -> Optional[CurriculumEvidence]:
        """Structured exact indicator-code lookup (highest authority)."""
        ...

    def retrieve_content_standard(
        self, request: EvidenceRequest
    ) -> Optional[CurriculumEvidence]:
        """Structured content-standard lookup (bounded fallback)."""
        ...

    def retrieve_keyword(
        self, request: EvidenceRequest, limit: int = 5
    ) -> List[CurriculumEvidence]:
        """Keyword/hybrid retrieval over the corpus (bounded by ``limit``)."""
        ...

    def name(self) -> str:
        """Stable provider identifier for provenance and diagnostics."""
        ...


# ── Current provider: the structured NaCCA exemplar corpus ───────────────────


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-']{2,}")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "their", "this", "that", "these", "those", "they", "them", "it", "its",
    "by", "as", "at", "from", "into", "using", "use", "able", "can", "will",
    "should", "which", "who", "how", "what", "when", "where", "why", "be",
    "is", "are", "was", "were", "has", "have", "had", "understand",
    "knowledge", "skill", "skills", "lesson", "learners", "learner",
    "students", "pupils", "including", "such", "correctly", "accurately",
    "about", "also", "each", "other", "others", "more", "most", "same",
    "between", "within", "through", "across", "among",
}


def _signal_terms(text: str, limit: int = 8) -> List[str]:
    """Significant content terms from raw text (for keyword retrieval)."""
    out: List[str] = []
    for w in _WORD_RE.findall(text or ""):
        lw = w.lower()
        if lw in _STOPWORDS or lw in out:
            continue
        out.append(lw)
        if len(out) >= limit:
            break
    return out


class StructuredExemplarProvider:
    """Evidence provider backed by the existing structured NaCCA corpus.

    This is the CURRENT retrieval implementation. It performs:

    1.  structured exact ``(subject, indicator_code)`` lookup — the highest
        authority match;
    2.  a bounded ``(subject, content_standard_code)`` fallback — only when
        the caller explicitly asks for it, and flagged ``match_type="standard"``;
    3.  keyword retrieval — subject-filtered term overlap over the corpus,
        flagged ``match_type="keyword"`` and never returned ahead of an exact
        match.

    No vector database, embedding service or hosted dependency is introduced;
    the corpus is an in-repo structured dataset. A future hybrid/semantic
    provider swaps in behind the same interface.
    """

    def name(self) -> str:
        return "structured-exemplar-corpus"

    def _corpus(self):
        from .exemplars import all_records  # local import keeps the layer thin
        return all_records()

    def _to_evidence(self, record, match_type: str) -> CurriculumEvidence:
        return CurriculumEvidence(
            provenance=EvidenceProvenance(
                source_type="official",
                source_name=record.source_title or "NaCCA Common Core Programme",
                subject=record.subject,
                level=record.level,
                indicator=record.indicator_code,
                version=record.source_version,
                location=record.source_url or record.provenance,
                note=record.provenance,
            ),
            learning_focus=record.learning_focus,
            curriculum_action_verbs=list(record.curriculum_action_verbs or []),
            exemplar_activity_patterns=[
                p for p in (record.exemplar_activity_patterns or []) if (p or "").strip()
            ],
            assessment_patterns=[
                p for p in (record.assessment_patterns or []) if (p or "").strip()
            ],
            assignment_patterns=[
                p for p in (record.assignment_patterns or []) if (p or "").strip()
            ],
            class_assignment_pattern=(record.class_assignment_pattern or "").strip(),
            home_assignment_pattern=(record.home_assignment_pattern or "").strip(),
            suitable_resource_patterns=[
                p for p in (record.suitable_resource_patterns or []) if (p or "").strip()
            ],
            focus_terms=[t for t in (record.focus_terms or []) if (t or "").strip()],
            core_competencies=[
                c for c in (record.core_competencies or []) if (c or "").strip()
            ],
            strand=record.strand,
            sub_strand=record.sub_strand,
            content_standard_code=record.content_standard_code,
            indicator_code=record.indicator_code,
            match_type=match_type,
        )

    # ── Protocol implementation ─────────────────────────────────────────

    def retrieve_exact(self, request: EvidenceRequest) -> Optional[CurriculumEvidence]:
        from .exemplars import lookup_indicator

        code = (request.indicator_code or "").strip()
        if not code:
            return None
        record = lookup_indicator(code, request.subject or "")
        if record is None:
            return None
        return self._to_evidence(record, "exact")

    def retrieve_content_standard(
        self, request: EvidenceRequest
    ) -> Optional[CurriculumEvidence]:
        from .exemplars import lookup_content_standard

        code = (request.content_standard_code or "").strip()
        if not code:
            return None
        record = lookup_content_standard(code, request.subject or "")
        if record is None:
            return None
        return self._to_evidence(record, "standard")

    def retrieve_keyword(
        self, request: EvidenceRequest, limit: int = 5
    ) -> List[CurriculumEvidence]:
        subject = (request.subject or "").strip().lower()
        if not subject:
            # Keyword search without a subject is refused: a code-free search
            # could return another subject's curriculum evidence.
            return []
        terms = [t for t in (request.terms or []) if (t or "").strip()]
        if not terms:
            return []
        wanted = {t.lower() for t in terms}
        scored: List[tuple] = []
        for record in self._corpus():
            if (record.subject or "").strip().lower() != subject:
                continue
            blob = " ".join(
                [
                    record.learning_focus or "",
                    record.strand or "",
                    record.sub_strand or "",
                    " ".join(record.focus_terms or []),
                ]
            ).lower()
            score = sum(1 for t in wanted if t in blob)
            if score > 0:
                scored.append((score, record))
        scored.sort(key=lambda pair: (-pair[0], pair[1].indicator_code))
        return [self._to_evidence(rec, "keyword") for _, rec in scored[:limit]]


# ── Registry / resolution ────────────────────────────────────────────────────

_PROVIDERS: Dict[str, CurriculumEvidenceProvider] = {}
_DEFAULT: Optional[CurriculumEvidenceProvider] = None


def register_evidence_provider(provider: CurriculumEvidenceProvider) -> None:
    """Register a retrieval implementation under its :meth:`name`.

    A future hybrid or semantic/vector RAG provider registers here. The lesson
    engine resolves evidence through :func:`get_evidence_provider` and never
    imports a backend directly, so the swap does not touch generation.
    """
    _PROVIDERS[provider.name()] = provider


def set_default_evidence_provider(provider: CurriculumEvidenceProvider) -> None:
    """Pin the provider used by :func:`get_evidence_provider` (tests/RAG)."""
    global _DEFAULT
    _DEFAULT = provider


def get_evidence_provider() -> CurriculumEvidenceProvider:
    """The active evidence provider (the structured corpus by default)."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = StructuredExemplarProvider()
        register_evidence_provider(_DEFAULT)
    return _DEFAULT


def evidence_for_lesson(
    request: EvidenceRequest,
    *,
    allow_standard_fallback: bool = False,
    provider: Optional[CurriculumEvidenceProvider] = None,
) -> Optional[CurriculumEvidence]:
    """Retrieve the SINGLE best curriculum evidence record for a lesson.

    Retrieval order is strict and authority-ranked:

    1.  exact indicator-code lookup (``match_type="exact"``);
    2.  (only when ``allow_standard_fallback``) the content-standard lookup
        (``match_type="standard"``);
    3.  nothing.

    Keyword matches are deliberately NOT returned here: an exact indicator
    match outranks vague semantic matches, so a keyword hit must never take the
    place of a real (absent) structured record. Keyword retrieval stays
    available directly through the provider for ranking/benchmarking.
    """
    prov = provider or get_evidence_provider()
    exact = prov.retrieve_exact(request)
    if exact is not None:
        return exact
    if allow_standard_fallback:
        return prov.retrieve_content_standard(request)
    return None


def request_from_lesson(alloc: Any, subject: str = "") -> EvidenceRequest:
    """Build an :class:`EvidenceRequest` from an allocated indicator row.

    Uses the allocation's OWN fields; never invents a code or level. The
    indicator's focus words become the keyword terms so a future hybrid
    provider has something to search on.
    """
    from .lesson_builder import strip_indicator_code  # local: avoid a cycle

    text = strip_indicator_code(getattr(alloc, "indicator_description", "") or "")
    return EvidenceRequest(
        subject=(subject or "").strip(),
        level="",
        indicator_code=(getattr(alloc, "indicator_code", "") or "").strip(),
        content_standard_code=(
            getattr(alloc, "content_standard_code", "") or ""
        ).strip(),
        terms=_signal_terms(text),
        source_week=getattr(alloc, "week_number", None),
    )


__all__ = [
    "CurriculumEvidence",
    "EvidenceProvenance",
    "EvidenceRequest",
    "CurriculumEvidenceProvider",
    "StructuredExemplarProvider",
    "register_evidence_provider",
    "set_default_evidence_provider",
    "get_evidence_provider",
    "evidence_for_lesson",
    "request_from_lesson",
]
