# REA-Powered Forensic Lesson-Planning Benchmark (Master Report)

**Task:** use the IDE's REA tooling to investigate high-performing lesson-planning
products and determine which observable mechanisms could make SchemeKnit require
even less teacher effort while preserving curriculum accuracy and deterministic
quality. **This was research + recommendations only — no SchemeKnit source changed.**

**Study:** 2026-10-14/15 · **Host:** win32 x64, Node 22.23.2, Chrome 155 ·
**Method:** REA `capture_browser_scenario` (Playwright/Chromium), REA
`analyze-javascript-application`, REA-derived sanitized network evidence ·
**Sub-reports:** `rea/REA_CAPABILITY_DISCOVERY.md`, `rea/UX_FLOW_MATRIX.md`,
`rea/NETWORK_AND_CLIENT_EVIDENCE.md`, `rea/LESSON_QUALITY_COMPARISON.md`,
`rea/SCHEMEKNIT_OPPORTUNITY_BACKLOG.md` · **Evidence:** `rea/evidence/`.

**Confidence labels used throughout:** `CONFIRMED` (captured response/DOM/bundle) ·
`OBSERVED` · `STRONGLY INFERRED` · `UNKNOWN`.

---

## 1. REA capabilities actually used

- **Discovery (`REA_CAPABILITY_DISCOVERY.md`):** installed `rea-agents@6.5.0`; opencode
  MCP registration **aligned**; 207 MCP tools / 153 CLI commands. The REA MCP tools
  are not exposed in this session's toolset, so the study used the **REA CLI**, which
  REA's own skill sanctions as the operator fallback. This substitution is recorded.
- **Used:** `capture-browser-scenario` (23 page captures; 1 interactive cascade),
  captured DOM + accessibility trees + 22 screenshots + network event lists, and
  `analyze-javascript-application` for static bundle reconstruction.
- **Unavailable on this host (recorded, not used):** Ghidra/IDA/Hopper (no engine),
  SQLite inspector (Node 22 < 24.15), Android JADX, macOS/Linux-only tooling.
- **Substitution used where needed:** Windows built-in WinRT OCR (en-US) to read
  SHS Planner's published sample lesson JPEGs (no OCR engine otherwise installed);
  recorded as a substitution.

## 2. Products inspected

**Tier 1:** GhanaEd (deep — home, register, planner, training + prior-session
generation), SHS Planner (deep — home, samples, guide, FAQ, guides, interactive
cascade, real 8-page lesson, bundle), Tenaly, Scorlar, Classpiler, StudyPlugHub Ghana.
**Tier 2:** MagicSchool, Eduaide, Planbook (+ help), Brisk Teaching.

## 3. Actual workflows tested

- **GhanaEd:** full registration wizard (captured), planner page, training doc;
  generation itself was exercised in the earlier session on our own account.
- **SHS Planner:** form examination + **live declared actions** (Year→Region select)
  via REA, capturing the curriculum cascade API; downloaded and OCR'd the real lesson.
- **All others:** public landing/solution/pricing/help pages and their interactive
  elements; generation behind logins not created → recorded as limitations.
- **SchemeKnit baseline:** its deterministic benchmark lesson reused; Autopilot
  selection code read for the decision-reduction analysis.

## 4. Screenshots / network evidence captured

- 22 screenshots (`evidence/screenshots/`), 23 normalized scenario summaries +
  accessibility + DOM texts (`evidence/scenarios/`), sanitized HAR-shaped network
  files (`evidence/har/`), 8 real lesson pages + OCR (`evidence/samples/`).
- **Sanitization:** REA retains URL query **names** only, header **names** only, no
  cookies/tokens/bodies; committed HAR files are derived summaries — no secrets.

## 5. Minimum-input comparison

- **SHS Planner's minimum = Year + Region + Subject + Week.** The week index resolves
  the whole NaCCA header client-side (`buildLsnMeta`). One decision → full header.
- **GhanaEd's minimum = the full cascade** (level→class→subject→term→strand→CS→
  indicator), though empty pickers auto-resolve server-side.
- **Tenaly** auto-populates the cascade and **caches per indicator**.
- SchemeKnit requires a **scheme upload** then Autopilot; it already resolves class/
  subject from the scheme and selects occurrences server-side. Full matrix:
  `rea/UX_FLOW_MATRIX.md` §3.

## 6. Lesson-output comparison

Only two **real** documents were legitimately inspectable: SHS Planner's published
8-page sample (scored 72/75, `NO/MINOR EDIT`) and GhanaEd's prior plans (55 and 45,
`MINOR`–`SUBSTANTIVE EDIT`). SchemeKnit's deterministic lesson scores 40/75
(`SUBSTANTIVE EDIT`) — strong provenance, weak prose/topic/timing. Detail:
`rea/LESSON_QUALITY_COMPARISON.md`.

## 7. Batch-generation comparison

- **GhanaEd:** bulk "generate for the whole term … confirm the cost, watch live
  progress" + background jobs + SSE series — `CONFIRMED` (prior session + training doc).
- **SHS Planner:** assessments/schemes-of-work builders; batch retries billed once
  with refunds — `CONFIRMED` (bundle).
- **SchemeKnit:** Autopilot (server-authoritative selection, quota-aware,
  accepted-only persistence) — `CONFIRMED` (source). Its batch *quality* gap, not its
  batch *capability*, is the issue.

## 8. Strongest teacher-effort-reduction findings

1. **Week-indexed curriculum resolution** (SHS Planner): one decision yields the
   whole header → fewest inputs observed.
2. **Differentiation + rubric woven into output** (SHS Planner): no post-editing.
3. **Per-indicator plan reuse** (Tenaly): the same lesson isn't regenerated/charged.
4. **Resilient streaming + refunds + auto-resume** (SHS Planner): poor networks don't
   burn teacher time or credits.
5. **Forgiving inputs with server resolution** (GhanaEd): never blocks on picker gaps
   (traded against its alignment defects).
6. **Zero-click handoff already in SchemeKnit** (`schemeknit.autopilot_intent` from
   the upload page): a foundation to extend to fully zero-decision generation for
   unambiguous schemes.

## 9. Strongest lesson-quality findings

- **SHS Planner** produces supervision-ready prose with DoK assessment and a rubric,
  and time-budgeted activities summing to the lesson length.
- **GhanaEd** produces rich, localised prose but corrupts the curriculum block
  (PDF artefacts, placeholder references, topic↔standard mismatch).
- **SchemeKnit** is the only one of the three with **provable provenance and exact
  indicator binding**; its weakness is purely the deterministic prose/topic/timing.

## 10. Confirmed facts vs inferences

**CONFIRMED:** all captured pages/endpoints; SHS Planner `/api/curriculum.php`,
`POST /api/generate.php` streaming contract, idle-abort/recovery/refund code,
`buildLsnMeta` week-resolution, the 8-page sample content; GhanaEd's 230+ routes and
API groups; SchemeKnit's Autopilot/quota/WAPEF logic.
**INFERRED/UNKNOWN:** generation internals/prompts of every tool (not inspected);
lesson quality of Tenaly/Scorlar/Classpiler/StudyPlugHub/MagicSchool/Eduaide/Brisk
(login-gated, not created); run-to-run variation (no repeat budget).

## 11. Top five SchemeKnit opportunities (ranked — detail in backlog)

1. **Deterministic prose hardening** — kill slot-fill artefacts, derive a real topic,
   enforce `Σ phase durations == duration`. *(B, priority 1)*
2. **Ghanaian localization bank** for deterministic mode. *(A, priority 2)*
3. **DoK-leveled assessment + rubric + woven differentiation**. *(A, priority 3)*
4. **Reuse & resilience** — per-source cache, resume, honest retry/refund semantics.
   *(B, priority 4)*
5. **Decision-reduction assessment** — remove only already-known-fact questions,
   keep WAPEF/needs-review interrupts. *(B/C, priority 5)*

## 12. What should NOT be copied

- GhanaEd's **PDF-sourced indicator/exemplar corruption** and placeholder references.
- **Pre-loaded national curriculum replacing scheme upload** (Scorlar/Tenaly pattern) —
  contradicts SchemeKnit's authority/provenance principle. *(D)*
- **Multi-model pedagogy choosers** (Eduaide) — added configuration burden. *(D)*
- **New vector DB / paid model / orchestration framework** — no evidence needed. *(D)*

## 13. Recommended next implementation task

Begin the **quality spine**: implement backlog item 1 (deterministic prose hardening +
real topic + timing invariant) with golden-file and invariant tests, because it
attacks the largest measured teacher effort (substantive editing) and is the safest,
most self-contained change. Then items 2–3.

## 14. Files created

- `docs/research/REA_LESSON_PLANNER_BENCHMARK.md` (this file)
- `docs/research/rea/REA_CAPABILITY_DISCOVERY.md`
- `docs/research/rea/UX_FLOW_MATRIX.md`
- `docs/research/rea/NETWORK_AND_CLIENT_EVIDENCE.md`
- `docs/research/rea/LESSON_QUALITY_COMPARISON.md`
- `docs/research/rea/SCHEMEKNIT_OPPORTUNITY_BACKLOG.md`
- `docs/research/rea/evidence/` — `screenshots/` (22 PNG), `scenarios/` (summary +
  accessibility + DOM texts per target), `har/` (sanitized summaries), `samples/`
  (8 SHS lesson pages + OCR + curriculum subjects JSON).

## 15. Repository state

- **No SchemeKnit source code changed.** New untracked files are limited to
  `docs/research/rea/**` and this report.
- No commits were made. No credentials/tokens/cookies committed (sanitized).
- No unauthorized access, no quota bypass; credit-limited and login-gated targets
  were recorded as limitations and skipped.

---

## Explicit answer

> **Based on observed evidence, what are the three largest remaining sources of
> teacher effort in SchemeKnit, and what is the smallest, safest implementation
> change that would eliminate the most work?**

**Three largest sources of teacher effort.**

1. **Substantive prose editing of deterministic lessons.** The benchmark lesson reads
   as slot-fill ("…using ;", "…process.."), so the teacher rewrites starter, teacher
   and learner actions, and activity text. `CONFIRMED` (`LESSON_QUALITY_COMPARISON.md`
   §2, §4). This is the biggest single effort.
2. **Fixing the lesson topic and the assessment/differentiation sections.** The topic
   is a strand/sub-strand concatenation ("DESIGN - CREATIVE AND DESIGN PROCESSES") and
   the assessment is one generic sentence with templated differentiation — the teacher
   rewrites all of it for supervision. `CONFIRMED`.
3. **Rework caused by incomplete timing and re-generation.** Deterministic phases
   account for only part of the lesson duration (32/50 min in the benchmark), and
   re-generating/repairing a weak lesson burns effort (and quota). `CONFIRMED`.

**Smallest, safest change that eliminates the most work.**

**Harden the deterministic lesson builder in one pass:** (a) render clauses only when
their slot is non-empty and normalise punctuation, (b) derive a real lesson topic from
the indicator + sub-strand (or require the teacher's explicit topic), and (c) assert
`Σ phase durations == duration_minutes` before the lesson ships. This lives entirely
inside the deterministic builder, changes **no** binding, provenance, quota or
persistence behaviour, keeps P4 and the "must work AI-OFF" constraint intact, and
directly converts the dominant `SUBSTANTIVE EDIT` into `MINOR EDIT`. It is item 1 in
`rea/SCHEMEKNIT_OPPORTUNITY_BACKLOG.md` and the recommended next task.

*Related: `rea/UX_FLOW_MATRIX.md` · `rea/NETWORK_AND_CLIENT_EVIDENCE.md` ·
`rea/LESSON_QUALITY_COMPARISON.md` · `rea/SCHEMEKNIT_OPPORTUNITY_BACKLOG.md` ·
`rea/REA_CAPABILITY_DISCOVERY.md`*