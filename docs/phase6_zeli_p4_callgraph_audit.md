# Phase 6 — Zeli / P4 quality-gate call-graph audit (2026-10-15)

Read-only verification of every `docs/QUALITY_GATE.md` claim about WHERE the
P4 gate runs and HOW it relates to Zeli (the optional AI layer). No code or
wording change was required — every claim checked out against the shipped
call graph.

## Verified call graph (batch generation, the only gate insertion point)

```
POST /generation/{scheme_id}/generate          routers/generation.py:625
  └─ GenerationPipeline.generate_all()         generation.py:859 → pipeline:129
       ├─ deterministic build (allocation + lesson_builder)   pipeline:220
       └─ AI enrichment, per lesson, ONLY when ai_mode != OFF
            (per-section schema validators + curriculum.quality_gate
             fallback to deterministic content on failure)    pipeline:396–558
  └─ drafts load + _apply_lesson_review_draft() per lesson    generation.py:921–923
  └─ _run_quality_gate(job, config, scheme_id, drafts)        generation.py:935
  └─ persist ONLY accepted candidates                         generation.py:2118–2231
```

Repo-wide grep confirms `generate_all` and `_run_quality_gate` have no other
production callers; Autopilot (`engines/autopilot.py`) is occurrence-selection
logic invoked through this same handler, not a second generation path.

## Claim-by-claim verification

| QUALITY_GATE.md claim | Evidence | Verdict |
|---|---|---|
| §2 "gate runs after `generate_all()` returns the final `job._lesson_plans` (post-AI, after drafts/hoisting), before persistence" | `generation.py:859` (generate_all) → `921–923` (drafts) → `935` (gate) → persistence of accepted only (`2207+`); AI enrichment is *inside* generate_all (`pipeline:437–557`) so it always precedes the gate when enabled | **ACCURATE** — "post-AI" is literally true: the gate evaluates whatever generate_all returned, AI-enriched or deterministic |
| §14 "Zeli never mandatory; Zeli never used to rescue weak deterministic lessons" | P4 rebuild loop calls deterministic `build_lesson` only (`generation.py:2144–2185`); AI OFF short-circuits before any provider (`pipeline:405–410`); frozen corpora run AI OFF / Zeli OFF at 100% teacher-ready | **ACCURATE** |
| §T/§108 "Zeli never used for WAPEF repair; WAPEF byte-identical post-gate" | WAPEF loss check compares against the saved draft canonical (`generation.py:2089–2107`, `2132–2133`); Zeli's lesson-level rewrite only receives the WAPEF value as a preservation constraint in the prompt (`ai_regeneration.py:707–727`) and metadata columns are never written by AI (`ai_regeneration.py:808`); rewrite failure preserves existing content (`ai_regeneration.py:889`) | **ACCURATE** |
| Zeli per-section rewrites are teacher-initiated polish on stored lessons (DEPLOYMENT.md §Zeli) | `ai_regeneration.py` — explicit-click endpoints, schema validators with one bounded retry, fail-preserved messages (`205–336`); no P4 re-run on this path, and no document claims one | **ACCURATE by design** — the P4 gate's scope is the generation path; a teacher-directed section rewrite is not a batch save, and invalid AI output is discarded, never merged |

## Findings

**NO-GAP.** The "post-AI" wording matches the real insertion point, the
Zeli-separation rules (never mandatory, never rescues, never WAPEF repair,
metadata never AI-written) all hold in code, and the single-path claim is
true (one generate_all caller, one gate caller; autopilot included). Phase 6
is a documented no-change verification commit.

Residual note (accepted design, not a defect): after a Zeli section rewrite
the lesson-level P4 gate is not re-run; the rewrite path's own validators and
preserve-on-failure semantics are the guard, and QA floors/timings are
metadata AI cannot touch.

## Verification

- Repo-wide caller grep: `generate_all`/`_run_quality_gate` production callers
  are exactly the documented ones.
- No production data touched; no thresholds, floors or fixtures changed.
