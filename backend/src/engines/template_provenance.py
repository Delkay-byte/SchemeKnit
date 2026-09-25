"""
Template provenance and verification registry.

The commercial rule: a template may be labelled official/approved ONLY when the
relevant approved source document exists and has been verified. Everything else
is a SchemeKnit standard template or pending verification. Provenance is declared
once here and consumed by the template registry (template_engine), the API
responses (routers/templates) and the documentation — never re-asserted ad hoc
where it can drift from the evidence.

Verification statuses
---------------------
``verified``              Backed by a supplied approved source document that has
                          been structurally analyzed (golden master) and whose
                          renderer output is compared against it.
``pending_verification``  A form SchemeKnit holds but whose approved
                          organizational source document has not been supplied.
``teachflow_standard``    Authored by SchemeKnit; no approval claim is made.

Labels shown to users map from the status:
``verified`` + approved source  -> "APPROVED ORGANIZATIONAL TEMPLATE"
``teachflow_standard`` status   -> "VERIFIED SchemeKnit STANDARD"
``pending_verification``        -> "PENDING SOURCE VERIFICATION"
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

# ── Provenance kinds ──────────────────────────────────────────────────────────

PROVENANCE_APPROVED_ORGANIZATIONAL = "approved_organizational"
PROVENANCE_TEACHFLOW_STANDARD = "teachflow_standard"

# ── Verification statuses ─────────────────────────────────────────────────────

VERIFICATION_VERIFIED = "verified"
VERIFICATION_PENDING = "pending_verification"
VERIFICATION_TEACHFLOW_STANDARD = "teachflow_standard"

#: User-facing labels, one per verification status.
VERIFICATION_LABELS = {
    VERIFICATION_VERIFIED: "APPROVED ORGANIZATIONAL TEMPLATE",
    VERIFICATION_PENDING: "PENDING SOURCE VERIFICATION",
    VERIFICATION_TEACHFLOW_STANDARD: "VERIFIED SchemeKnit STANDARD",
}


@dataclass(frozen=True)
class TemplateProvenance:
    """Evidence-based provenance record for one built-in template."""

    template_id: str
    provenance: str
    verification_status: str
    #: True only when an approved source document exists AND has been verified.
    official: bool
    #: Path (repo-relative) of the authoritative source document, when one exists.
    source_document: Optional[str] = None
    #: What the evidence actually is, in one sentence.
    evidence: str = ""
    #: Class levels the template applies to (empty = whole educational family).
    levels: Tuple[str, ...] = ()

    @property
    def verified(self) -> bool:
        return self.verification_status == VERIFICATION_VERIFIED

    @property
    def label(self) -> str:
        return VERIFICATION_LABELS[self.verification_status]

    def as_dict(self) -> dict:
        return {
            "provenance": self.provenance,
            "verification_status": self.verification_status,
            "verified": self.verified,
            "official": self.official,
            "provenance_label": self.label,
            "source_document": self.source_document,
            "evidence": self.evidence,
            "levels": list(self.levels),
        }


# ── Registry ──────────────────────────────────────────────────────────────────
#
# Evidence notes state exactly what backs each template. All four bundled forms
# are real GES/NaCCA lesson-plan documents (each prints its own GES/NaCCA title
# and is structured as a token form: bracketed placeholders inside its tables).
# Each has been structurally fingerprinted from the file itself and its renderer
# verified to fill the form in place with no surviving placeholder tokens and no
# change to the source's table topology — so output matches the source by
# construction. The JHS form additionally is the approved organizational source
# supplied by the headteacher; the other three are the official GES/NaCCA forms
# for their levels.

PROVENANCE_REGISTRY: Dict[str, TemplateProvenance] = {
    "tpl-official-ges-nacca-jhs": TemplateProvenance(
        template_id="tpl-official-ges-nacca-jhs",
        provenance=PROVENANCE_APPROVED_ORGANIZATIONAL,
        verification_status=VERIFICATION_VERIFIED,
        official=True,
        source_document="backend/src/engines/assets/ges_jhs_lesson_plan_template.docx",
        evidence=("Approved lesson-plan document supplied by the organization/headteacher; "
                  "its structure is fingerprinted from the file itself (4 tables, no "
                  "merges, tridelivery timeline) and its renderer fills the form in "
                  "place, so output topology matches the source by construction."),
        levels=("Basic 7", "Basic 8", "Basic 9"),
    ),
    "tpl-approved-org-headteacher": TemplateProvenance(
        template_id="tpl-approved-org-headteacher",
        provenance=PROVENANCE_APPROVED_ORGANIZATIONAL,
        verification_status=VERIFICATION_VERIFIED,
        official=True,
        source_document="backend/src/engines/assets/ges_jhs_lesson_plan_template.docx",
        evidence=("Alias of the verified approved JHS source document: the same file is "
                  "rendered in place, so no second hand-written layout exists that can "
                  "drift from the golden master."),
        levels=("Basic 7", "Basic 8", "Basic 9"),
    ),
    "tpl-wapef-approved-plan": TemplateProvenance(
        template_id="tpl-wapef-approved-plan",
        provenance=PROVENANCE_APPROVED_ORGANIZATIONAL,
        verification_status=VERIFICATION_VERIFIED,
        official=True,
        source_document="backend/src/engines/assets/wapef_approved_plan_template.docx",
        evidence=("Approved WAPEF lesson-plan document supplied by WAPEF; its "
                  "structure (7x6 metadata table, 3x3 + 4x3 phase grids, merges "
                  "and labels) is reproduced from the source file itself — blank "
                  "value cells were tokenized in place, so the renderer's output "
                  "topology matches the source by construction. The completed "
                  "WAPEF Science sample is the populated acceptance fixture."),
        levels=("Nursery", "KG 1", "KG 2", "Basic 1", "Basic 2", "Basic 3",
                "Basic 4", "Basic 5", "Basic 6", "Basic 7", "Basic 8", "Basic 9"),
    ),
    "tpl-official-ges-nacca-kg": TemplateProvenance(
        template_id="tpl-official-ges-nacca-kg",
        provenance=PROVENANCE_APPROVED_ORGANIZATIONAL,
        verification_status=VERIFICATION_VERIFIED,
        official=True,
        source_document="backend/src/engines/assets/ges_kg_lesson_plan_template.docx",
        evidence=("Official GES/NaCCA Kindergarten lesson-plan form: the file prints its "
                  "own GES/NaCCA title and is a token form (2 tables, play-based "
                  "delivery grid). Fingerprinted from the file itself; its renderer "
                  "fills the form in place with no surviving tokens and unchanged "
                  "table topology."),
        levels=("Nursery", "KG 1", "KG 2"),
    ),
    "tpl-official-ges-nacca-primary": TemplateProvenance(
        template_id="tpl-official-ges-nacca-primary",
        provenance=PROVENANCE_APPROVED_ORGANIZATIONAL,
        verification_status=VERIFICATION_VERIFIED,
        official=True,
        source_document="backend/src/engines/assets/ges_primary_lesson_plan_template.docx",
        evidence=("Official GES/NaCCA Lower Primary lesson-plan form: the file prints "
                  "its own GES/NaCCA title and is a token form (2 tables, "
                  "starter/main/plenary delivery grid). Fingerprinted from the file "
                  "itself; its renderer fills the form in place with no surviving "
                  "tokens and unchanged table topology."),
        levels=("Basic 1", "Basic 2", "Basic 3"),
    ),
    "tpl-official-ges-nacca-shs": TemplateProvenance(
        template_id="tpl-official-ges-nacca-shs",
        provenance=PROVENANCE_APPROVED_ORGANIZATIONAL,
        verification_status=VERIFICATION_VERIFIED,
        official=True,
        source_document="backend/src/engines/assets/ges_shs_lesson_plan_template.docx",
        evidence=("Official GES/NaCCA Senior High School lesson-plan form: the file "
                  "prints its own GES/NaCCA title and is a token form (2 tables, CCP "
                  "academic delivery grid). Fingerprinted from the file itself; its "
                  "renderer fills the form in place with no surviving tokens and "
                  "unchanged table topology."),
        levels=("SHS 1", "SHS 2", "SHS 3"),
    ),
}

# Custom (teacher-uploaded) templates are never official.
_CUSTOM_TEMPLATE_PROVENANCE = TemplateProvenance(
    template_id="<custom>",
    provenance=PROVENANCE_TEACHFLOW_STANDARD,
    verification_status=VERIFICATION_TEACHFLOW_STANDARD,
    official=False,
    evidence="Teacher-uploaded or teacher-authored template; no approval claim.",
)


def provenance_for_template(template_id: Optional[str], is_custom: bool = False) -> TemplateProvenance:
    """Provenance record for a template id.

    Unknown built-in ids fall back to the SchemeKnit-standard record rather than
    inheriting any approval claim — approval must be declared, never assumed.
    """
    if is_custom:
        return _CUSTOM_TEMPLATE_PROVENANCE
    record = PROVENANCE_REGISTRY.get(template_id or "")
    if record is not None:
        return record
    return TemplateProvenance(
        template_id=template_id or "",
        provenance=PROVENANCE_TEACHFLOW_STANDARD,
        verification_status=VERIFICATION_TEACHFLOW_STANDARD,
        official=False,
        evidence="No provenance declared; treated as a SchemeKnit standard template.",
    )


def provenance_summary() -> dict:
    """Bucket view used by the acceptance report and API diagnostics."""
    buckets = {
        "verified_approved": [],
        "teachflow_standard": [],
        "pending_verification": [],
    }
    for record in PROVENANCE_REGISTRY.values():
        if record.verification_status == VERIFICATION_VERIFIED:
            buckets["verified_approved"].append(record.template_id)
        elif record.verification_status == VERIFICATION_PENDING:
            buckets["pending_verification"].append(record.template_id)
        else:
            buckets["teachflow_standard"].append(record.template_id)
    return buckets
