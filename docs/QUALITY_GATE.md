# Priority 4 — Deterministic Lesson Quality Gate (v1.0)

## 1. Purpose

The Priority 4 quality gate makes deterministic lesson generation **self-checking and self-correcting**. After generation (post-AI), a deterministic gate evaluates each lesson plan against hard structural/curriculum invariants and a calibrated teacher-ready rubric. Weak deterministic lessons are **never saved**: mechanical repair is attempted first (only when failing), then bounded deterministic rebuild with alternate teaching patterns (≤2 candidates), followed by deterministic best-candidate selection. Only **accepted** candidates persist; rejected lessons consume **0 quota units** and existing rows are left unchanged (accept-scoped replacement). The system remains fully usable with AI OFF / Zeli OFF.

## 2. Insertion Point (Generation Pipeline)

The gate runs **after** `engines/generation_pipeline.py::generate_all()` returns the final `job._lesson_plans` (post-AI, after drafts/hoisting) and before persistence:

1. **Draft hoist (pre-pass):** `_apply_lesson_review_draft()` is applied to each final lesson (drafts take precedence where present).
2. **Ledger present:** `generation_pipeline` passes `allocation_engine.BuildLedger` (with per-lesson `BuildContext{alloc, previous_indicator, next_indicator, pattern_id, history}`) via `job._build_ledger`. `allocation_engine.generate_lesson_plans(..., ledger=...)` records contexts and build history.
3. **Gate evaluation:** `src/routers/generation.py::_run_quality_gate()` orchestrates evaluation, mechanical repair, bounded rebuild loop, best-candidate selection, and metrics aggregation.
4. **Accept-scoped persistence:** **Only accepted candidates** are persisted. Rejected lessons do not overwrite existing DB rows (replacement/re-homing is accept-scoped). Total rejection → HTTP 500, no lessons saved, **quota consumed = 0**.
5. **Quota semantics:** Quota reserve key = `scheme:code` (repeated cross-week code = 1 unit; indicatorless = 0). Reserve before build; on hard failure/rebuild exhaustion, units are released (0 consumed). On success of an accepted lesson, **1 unit** consumed.

## 3. Hard Failures (A–X)

The gate enforces hard structural/curriculum invariants (`src/engines/lesson_quality_gate.py`). Early-years (Nursery/KG) bypass curriculum-provenance checks the source cannot supply (missing Content Standard/prose-indicator assumptions) and use a structural-only gate; indicatorless lessons relax provenance appropriately. A failure in any hard category **rejects** the lesson (mechanical repair attempted first, else rebuild, else rejection).

| Code | Failure | Notes |
|---|---|---|
| A | `wrong_source_occurrence` | Source occurrence/index mismatch vs BuildContext. |
| B | `missing_content_standard_code` | Content Standard code missing vs allocation (non-early-years; source-dependent; skipped where legitimately absent). |
| C | `missing_content_standard_text` | Content Standard description missing. |
| D | `missing_indicator` | Lesson indicator empty/malformed. |
| E | `missing_objective` | Objective missing or effectively empty. |
| F | `objective_not_related_to_indicator` | Objective weakly/incorrectly related to source indicator (indicator-interpreter based; not naive substring). |
| G | `objective_too_generic` / `generic_objective` | Objective is generic ("learners can explore/understand/discuss/learn/talk about/know/be aware…") per canonical rubric. |
| H | `missing_phase1` | Phase 1 (starter/introduction) missing required structure. |
| I | `missing_phase2` | Phase 2 (main/development) missing. |
| J | `missing_phase3` | Phase 3 (plenary/closure) missing. |
| K | `missing_learner_action` | No concrete learner action in structured activities/phase prose. |
| L | `missing_teacher_action` | Insufficient teacher guidance/actions. |
| M | `invalid_duration` | Duration out of range or inconsistent with structure. |
| N | `incomplete_timing` | Phase sums ≠ lesson duration OR step sums ≠ phase duration. |
| O | `unresolved_placeholder` | Bracketed placeholders (`[...]`, `{...}`, `TODO`, `TBA`) remain unresolved. |
| P | `filler_text` | Excess filler/redundant boilerplate detected. |
| Q | `empty_activity` | Activity row has empty description/learner action. |
| R | `invalid_resource_shape` | Resource entries malformed (missing name/type/format constraints). |
| S | `missing_assessment` | Assessment missing or non-specific. |
| T | `wapef_loss` | **Only** when a **saved WAPEF selection exists** for that lesson and canonical WAPEF values differ from the saved selection (empty state is legitimate). Zeli **never** used for WAPEF repair. |
| U | `source_week_occurrence_mismatch` | Week/occurrence inconsistent with allocation context. |
| V | `duplicate_or_corrupted_fields` | Duplicate/corrupted structured fields detected. |
| W | `export_critical_malformed_structure` | Export-critical structure cannot be rendered safely (DOCX/PDF). |
| X | `curriculum_provenance_missing` | Provenance required by source cannot be satisfied (non-early-years). |

## 4. Teacher-Ready Rubric (Canonical, Unchanged)

The gate reuses the **existing P2 15-criterion rubric canonically** (extracted to `src/curriculum/lesson_rubric.py`; benchmarks re-export it). No conflicting rubric was introduced. The same rubric drives both frozen-benchmark acceptance and gate scoring.

**Required floors (teacher-ready gate):**
```text
timing_integrity        >= 5
objective_specificity    >= 4
topic_specificity       >= 3
phase1_usefulness       >= 3
phase2_usefulness       >= 3
phase3_usefulness       >= 3
assessment_alignment    >= 3
resource_realism        >= 3
```

A lesson is **teacher-ready** (and eligible for acceptance after passing all hard failures) only when every required floor is met **and** no hard failures remain. Soft-floor failures alone produce `soft_rejections` (floors_failed) and the candidate is rejected unless rebuild produces a candidate that clears all floors + all hard failures.

## 5. Mechanical Repair (Only on Failure)

When a lesson **fails** evaluation, the gate first attempts **mechanical repair** (`mechanical_repair()`):
- Whitespace/punctuation normalization (collapse spaces, fix spacing before punctuation, collapse repeated punctuation, remove empty parens, trim trailing punctuation runs) — **cosmetic only**.
- Structural deduplication (merge duplicate activity/resource rows; minutes preserved on merge — sum of rows is never silently dropped).
- Boundary restoration (restore missing starter/conclusion rows from starter/conclusion text when structure drifted).
- Non-structural text cleanups only. **Repairs are never applied to lessons that pass** the gate on first evaluation (the flow does not rewrite good output).

Repairs are logged per field (`repairs` list) and the lesson is re-evaluated immediately after repair. If it becomes accepted → `repaired` (not rebuilt). If still failing → proceed to deterministic rebuild.

## 6. Deterministic Rebuild (Bounded, ≤2 Candidates)

If repair fails to produce an accepted lesson, the gate attempts **bounded deterministic rebuild** using alternate teaching patterns:
- **Initial build context preserved:** `BuildContext` (alloc with source_text, previous_indicator, next_indicator, pattern_id, history) is carried through.
- **Alternate patterns only:** `pick_alternate_pattern()` selects a different pattern from the same alloc/config; **tried pattern IDs are excluded** across attempts.
- **Bounded:** At most **MAX_REBUILD_ATTEMPTS = 2** additional candidates (initial + ≤2 rebuilds). The loop is caller-enforced (router never requests > 2). Attempts are counted per lesson (`attempts = 1 + rebuild count`).
- **Deterministic:** No randomness; selection is order-deterministic (by pattern order/availability with exclusions). 
- **Rebuild never invents fixes for source-level genericity:** Curriculum fidelity overrides style. For example, `generic_objective` derived from a weak source indicator cannot be mechanically "fixed" by pattern alternation in a way that violates the canonical rubric; such cases remain unrecoverable within ≤2 candidates.
- **Early-years:** Pattern-less early-years lessons follow builder/pattern-engine behavior (no forced pattern rebuild when no patterns exist).

Each rebuilt candidate is:
1. Rebuilt via allocation/generation with the alternate pattern (ledger/history updated),
2. Drafts **re-applied** (`_apply_lesson_review_draft`) to the rebuilt candidate,
3. Evaluated independently (hard failures + rubric floors).

## 7. Best-Candidate Selection (Deterministic, Tie-Breakers)

When multiple candidates (original + up to 2 rebuilt) are produced/evaluated, the gate selects the **best accepted** candidate deterministically by priority key:
1. **Curriculum alignment** (prefer candidates with stronger indicator/objective relation; respect canonical objective checks)
2. **Subject pedagogy** (fit to subject/class/phase structure)
3. **Activity specificity** (concrete learner actions over vague)
4. **Assessment alignment** (stronger alignment to objective/indicator)
5. **Rubric total** (higher total score first)
6. **Fewer structural repetitions** (prefer less duplication in activities/phases)
7. **Source order** (preserve original allocation/source order on ties)

**Tie on all:** keep the **first** candidate in source order (deterministic). No randomness. Curriculum fidelity always overrides stylistic preferences.

## 8. WAPEF Loss Semantics (Critical)

`wapef_loss` (T) fails **only** when a **saved WAPEF selection exists** for that lesson **and** the lesson's canonical WAPEF values differ from that saved selection. 
- **Empty state is legitimate** (no saved selection yet) — does **not** trigger WAPEF loss.
- **Zeli is banned** from WAPEF repair. WAPEF values remain **byte-identical** post-gate (acceptance path preserves canonical WAPEF).
- This preserves `test_wapef_save_boundary` (group G) semantics.

## 9. Quota, Persistence & Replacement

- **Reserve before build:** `scheme:code` key (repeated cross-week code = 1 unit; indicatorless = 0).
- **On failure/rebuild exhaustion (no accepted candidate):** **0 quota units consumed** (unused keys released). No lesson is persisted.
- **On acceptance:** **1 quota unit** consumed (per accepted lesson).
- **Persist ONLY accepted candidates.** Rejected candidates are never written to DB.
- **Accept-scoped replacement/re-homing:** When replacing an existing lesson row (same scheme/week/occurrence or re-homed), the replacement occurs **only for accepted candidates**. Rejected lessons keep their existing rows unchanged.
- **Total rejection of a generation run:** Returns **HTTP 500**, with **no lessons saved**, **no quota consumed**, and existing persisted lessons for that scheme unaffected (idempotent, non-destructive).
- **Drafts:** Hoisted before gate evaluation; re-applied to any rebuilt candidates.

## 10. Calibration (Frozen Corpora, AI OFF / Zeli OFF)

Calibration was performed against **frozen baselines** (HEAD `8fb169a`, baselines captured **before** any P4 code changes). Gate metrics below were produced by running the exact router gate (`routers.generation._run_quality_gate`) over the three frozen corpora via `tests/gate_metrics.py`.

**Baselines (frozen):**
- `docs/benchmark/after.json` (11-lesson): **11/11 (100%)**, mean rubric **73.7/75**, `{}` rejections
- `docs/benchmark/hardening_after.json` (expanded 40 + messy 19): expanded **31/40 (77.5%)**, **71.7/75**; messy **12/19 (63.2%)**, **69.6/75** (7 generic_objective failures)

**Post-gate calibration (this build):**
```text
11-lesson (11): accepted 11/11, first-pass 11, repaired 0, rebuilt 0, rejected 0
  first-pass 100%, teacher-ready 100%, mean 73.7/75, mean rebuilds 0.00
  hard_rejections: {}  soft_rejections: {}  repairs: {}

expanded-40 (40): accepted 31/40, first-pass 31, repaired 0, rebuilt 0, rejected 9
  first-pass 77.5%, teacher-ready 77.5%, mean 71.7/75, mean rebuilds 0.00
  hard_rejections: generic_objective×7
  soft_rejections: objective_specificity<4×9
  repairs: {}

messy-19 (19): accepted 12/19, first-pass 12, repaired 0, rebuilt 0, rejected 7
  first-pass 63.2%, teacher-ready 63.2%, mean 69.6/75, mean rebuilds 0.00
  hard_rejections: generic_objective×7
  soft_rejections: objective_specificity<4×7
  repairs: {}
```

**Calibration evidence file:** `docs/benchmark/gate_metrics.json` (machine-readable).

**Notes on rebuilds:** In these frozen corpora, the failing lessons' hard failures (`generic_objective` derived from source indicator) were **not recoverable** by alternate patterns within ≤2 candidates (curriculum fidelity constraint). Consequently `mean_rebuilds = 0.00` in the summary above (rebuild loop executed but produced no accepted alternative within bound, resulting in rejection). The bounded rebuild path is implemented and exercised by unit tests (`tests/test_quality_gate.py::TestDeterministicRebuild`).

## 11. Timing Matrix

The gate's per-lesson evaluation is deterministic and cheap (structural checks + rubric scoring + optional mechanical repair + up to 2 rebuild evaluations). The implementation targets the documented timing envelope: **30–80ms** per lesson in typical cases (benchmarked in unit tests). No external AI calls occur in the gate path (AI is post-generate by design; gate is deterministic).

## 12. Early-Years Behavior

Nursery/KG lessons:
- Skip curriculum-provenance checks the source cannot supply (missing Content Standard code/prose-indicator provenance assumptions).
- Apply **structural-only** gate (hard failures limited to structural/invariants that can be verified).
- No forced pattern rebuild when no teaching patterns exist (mirror builder/pattern-engine behavior).

## 13. Metrics Exposed

`_run_quality_gate()` returns:
```python
{
  "reports": [PerLessonReport(... status, attempts, total, hard_failures, floors_failed, repairs, rebuild_pattern_ids, ...)],
  "metrics": {
      "lessons": int,
      "accepted": int, "rejected": int,
      "first_pass": int, "repaired": int, "rebuilt": int,
      "hard_rejections": {code: count}, "soft_rejections": {name: count}, "repairs": {type: count},
      "first_pass_rate": float, "teacher_ready_rate": float, "mean_score": float, "mean_rebuilds": float,
  },
}
```

The router includes `quality` metrics in the generation response (when reporting per-lesson results) for observability. No PII is logged.

## 14. Non-Goals (P4 Hard DO-NOTs)

- No Generate-page redesign, Autopilot redesign, quota-rule change, or WAPEF save-boundary change.
- No Groq provider architecture change.
- Zeli **never** mandatory; Zeli **never** used to rescue weak deterministic lessons.
- No second lesson representation, no vector DB, no paid deps.
- Do **not** rewrite P2 composition architecture (gate is a validation/recovery layer around it).
- Production claim deferred (§24): Render build is stale vs local (marker driver confirms). No P4 production deployment claim in this report.

## 15. Verification (What Passes)

- `tests/test_quality_gate.py`: 58 passed (adversarial A–X ≥20, mechanical repair, bounded deterministic rebuild ≤2, best-candidate ranking + ties + collisions, timing matrix 30–80, calibration guard, endpoint integration with total-rejection path).
- `tests/test_wapef_save_boundary.py`: 11 passed (WAPEF loss semantics preserved; empty state legitimate).
- Full backend suite (non-environmental): **2366 passed, 11 skipped** excluding the single known live-Groq environmental rate-limit case (`TestLiveGroq::test_one_indicator_structured_generation` — observed as environmental per §25). All core generation/persistence/autopilot/KG/Nursery/WAPEF/remediation remain green.
- Frozen benchmarks byte-identical post-rubric extraction; calibration metrics match frozen baselines.

## 16. Answer to Mandated Question

**Does SchemeKnit now automatically prevent weak deterministic lessons from being saved?**  
**Yes.** The P4 quality gate enforces hard failures (A–X), requires all teacher-ready rubric floors to be met, attempts only mechanical repair (on failure) then bounded deterministic rebuild (≤2 candidates, deterministic selection, curriculum fidelity preserved), and **persists only accepted candidates**. Rejected lessons consume **0 quota units**, existing rows remain unchanged (accept-scoped), and total rejection fails the run without saving anything. With AI OFF / Zeli OFF fully usable, weak deterministic lessons are automatically prevented from being saved.
