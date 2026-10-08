# GhanaEd vs SchemeKnit — Benchmark Comparison (Forensic Study)

Study date: 2026-10-06 · Basis: three captured artifacts on one benchmark topic
(`B9.1.3.1.1 Plan and execute design projects using the creative process.`):

| ID | Artifact | Config |
|---|---|---|
| **G-A** | `ghanaed_plan_A.json` | GhanaEd, B7, empty curriculum pickers (server auto-resolved), AI generation, 10 credits |
| **G-B** | `ghanaed_plan_B.json` | GhanaEd, B9, topic = benchmark indicator, cascade mis-picked (`1 DESIGN`, empty sub-strand/CS), AI generation, 10 credits |
| **SK** | `schemeknit_benchmark_lesson.json` (+ `_provenance.json`) | SchemeKnit local (own system), synthetic `sk_b9_creative_arts_scheme.docx` uploaded → detection → single-indicator selection, **AI mode OFF** (deterministic builder), free-tier quota 1/5 used |

**Honesty constraints (per brief):** GhanaEd ran with only 20 free credits →
`n=1` per run, no repeats (GENERATION_FORENSICS §6). SchemeKnit ran
**deterministic (AI OFF)** because no AI provider is configured on the local
instance; whether SchemeKnit AI mode closes the prose gaps is
**POSSIBLE-UNCONFIRMED**. Scores are 1–5 per criterion (5 = teacher needs no
edit), assigned strictly from the JSON artifacts.

---

## 1. Benchmark scores (15 criteria)

| # | Criterion | G-A | G-B | SK | Decisive evidence |
|---|---|---|---|---|---|
| 1 | Curriculum/indicator alignment | 2 | 1 | **5** | G-B topic says B9.1.3.1.1 but objectives/CS are B9.1.1.1.x; G-A `indicators:[]`; SK `indicator_codes:["B9.1.3.1.1"]` exact |
| 2 | Metadata completeness | 2 | 2 | **4** | G-A/B `weekEndingDate:""`, `classSize:0`; SK `week_ending 2026-10-09`, `lesson_date`, `class_size:30` (SK `school_name:""` — config not supplied) |
| 3 | Objective quality | **4** | 3 | 3 | G-A 3 concrete objectives; G-B codes belong to wrong indicators; SK 1 objective = verbatim indicator rephrase ("Learners can Plan…" casing glitch) |
| 4 | Time-budget integrity | **5** | **5** | 2 | G-A/B 10+30+10 = 50 = `duration`; SK main phases 11+14+7 = 32 of 50 min (18 unaccounted) |
| 5 | Activity specificity | **4** | **4** | 2 | G-A word-game warm-up, group roles; G-B kingfisher biomimicry research; SK slot-fill prose ("…using ; the teacher supports") |
| 6 | Ghanaian contextualization | **4** | **4** | 1 | G-A "African fabric design", artisans; G-B Shinkansen/palm-tree/traditional architecture; SK none |
| 7 | Resources/TLR fidelity | 3 | 3 | **5** | G-A/B generic "Chalkboard…"; SK carries scheme TLRs labelled `source_tlrs` + conservative additions |
| 8 | Assessment quality | **4** | **4** | 3 | per-phase formative checks in G-A/B; SK single generic rubric sentence |
| 9 | Differentiation | **4** | **4** | 3 | G-A/B support/core/challenge triples; SK present but templated with artifacts |
| 10 | Text integrity (no corruption) | **5** | 2 | 3 | G-B PDF page furniture in `indicators[]`/`exemplars[]`; SK double periods + empty-slot fragments; G-A clean |
| 11 | References integrity | 3 | 1 | 2 | G-B literal placeholder "NaCCA / GES curriculum title…"; G-A generic-but-plausible; SK `references:[]` empty |
| 12 | Lesson topic quality | 3 | 3 | 1 | G-A/B topic = indicator text (usable); SK topic = "DESIGN - CREATIVE AND DESIGN PROCESSES" (strand concat, not a topic) |
| 13 | Requested-context consistency | 4 | 2 | **5** | G-B picker/topic contradiction; SK scheme+config fully consistent (`provenance` chain) |
| 14 | Required-field completeness | **5** | **5** | 4 | G-A/B fill PI, RPK, competencies, keywords, homework, notes, warm-up, QA, real-life; SK has RPK/competencies/keywords/homework but empty `essential_questions`/`remarks`, no named PI field |
| 15 | Overall edit-to-use readiness | **3** | 2 | 2 | G-A: fix indicators/references/metadata; G-B: fix curriculum block + references + topic alignment; SK: needs a real topic, prose polish, timing fix |
| | **Total (max 75)** | **55** | **45** | **45** | |

### Reading the numbers honestly
- **G-A wins** because its pedagogy/localization/metadata-of-prose is what
  teachers feel when they "barely edit"; its weak point (empty indicators,
  generic references) is invisible in print unless a supervisor checks codes.
- **G-B ties SK** for different reasons: G-B's prose is excellent but its
  curriculum block is *wrong and visibly corrupted*; SK's curriculum wiring is
  *perfect but its prose is robotic*. A teacher comparing printed pages would
  still prefer G-B's body text — hence the qualitative verdict below.
- Caveat: had G-B's cascade been picked correctly (no third run possible —
  credits), criteria 1/13 would likely rise sharply and G-B would pull ahead
  (**POSSIBLE-UNCONFIRMED**). SK AI mode untested (**POSSIBLE-UNCONFIRMED**).

## 2. Why GhanaEd teachers "need little editing" (qualitative)

1. **Server completes every prose field from minimal input** — the teacher's
   real job is a topic string; curriculum fields, PI, RPK, competencies,
   warm-up script, QA pairs, differentiation, homework and teacher notes are
   all emitted, non-empty (CONFIRMED in both plans).
2. **GES-format daily skeleton** — fixed 10/30/10 phase structure with
   per-step minute rows *and* pre-rendered `activities` strings, matching the
   paper lesson-note format teachers submit; plus a `printTemplateId`
   (jhs-daily/primary-ges) so the artifact prints/submits directly (CONFIRMED).
3. **Ghanaian localization by default** — artisans, African fabric, local
   architecture examples without asking (CONFIRMED in both plans).
4. **Forgiving inputs** — empty pickers auto-resolve; generation never blocks
   on curriculum nuance (CONFIRMED Gen A). Speed-to-result beats strictness
   for the target user (OBSERVED).
5. **Print-first completeness beats alignment** — the defects that remain
   (codes, references, blanks) are *metadata*, not visible prose, so the
   printed page looks finished (STRONGLY INFERRED as the product priority).

## 3. Why SchemeKnit has struggled (relative to this benchmark)

1. **Deterministic prose = slot-fill** — indicator text interpolated into
   template clauses produces "…using ;", "…process..", repeated verbatim
   objective in every sentence (CONFIRMED in SK artifact).
2. **No localization layer** in deterministic mode (CONFIRMED absent).
3. **Timing invariant not enforced** — phase durations sum ≠ lesson duration
   (CONFIRMED: 32/50).
4. **Topic derivation weak** — strand/sub-strand concat instead of a lesson
   topic (CONFIRMED).
5. **Stricter entry path** — requires a scheme document upload + detection +
   quota accounting before anything prints, where GhanaEd allows ad-hoc
   generation (CONFIRMED both flows). SchemeKnit's strictness is exactly what
   makes its *alignment* stronger (its provenance chain is complete —
   `schemeknit_benchmark_provenance.json`) — this is a feature to keep, not
   remove.
6. (Context) persistence/Save-Review defects from the paused remediation wave
   are orthogonal to generation quality and were not re-tested this session.

## 4. Recommendations for SchemeKnit (ranked, with confidence)

| # | Recommendation | Confidence | Basis |
|---|---|---|---|
| 1 | **Keep strict curriculum binding** (never emit a lesson against unresolved/mismatched indicators; GhanaEd's Gen-B failure is the case study) | CONFIRMED | §1 criteria 1/13 |
| 2 | **Graceful slot-fill**: drop/skip clauses whose slot is empty; post-render punctuation normalization | CONFIRMED defect | SK artifacts, criterion 5/10 |
| 3 | **Enforce `sum(phase durations) == duration_minutes`** at build time | CONFIRMED defect | criterion 4 |
| 4 | **Derive a real lesson topic** (teacher input required, or template from indicator + substrand, never strand concat) | CONFIRMED defect | criterion 12 |
| 5 | **Ghanaian localization pack** for deterministic mode (region/craft/festival example banks keyed by subject) | STRONGLY INFERRED as GhanaEd's main edge | criterion 6 |
| 6 | **Emit/print GES-format daily template** with pre-rendered activities + one-click print (GhanaEd `jhs-daily` analogue) | STRONGLY INFERRED | UX/quality §2.2 |
| 7 | **Reference resolution**: fill from scheme resources + curriculum citation (never empty, never placeholder text) | CONFIRMED defect both sides | criterion 11 |
| 8 | **AI as prose enricher over the deterministic spine** (GhanaEd's apparent architecture: server resolves curriculum, AI writes prose) + keep provenance stamps | STRONGLY INFERRED | ARCHITECTURE §2, GENERATION §1 |
| 9 | Surface the **quota/preview transparency** SchemeKnit already has (preview showed selectable indicators + quota before spend) — a trust win over GhanaEd's post-hoc debit | CONFIRMED | our benchmark run logs |
| 10 | Optionally add **forgiving ad-hoc mode** (topic-only generation with server-side resolution) as an explicit "quick draft" tier, clearly labelled as unaligned draft | POSSIBLE-UNCONFIRMED value | GhanaEd Gen-A pattern |

## 5. Verdict (confidence-labelled)

- **Content craft & print-readiness: GhanaEd ahead** (OBSERVED, n=2).
- **Curriculum integrity & lineage: SchemeKnit ahead** (CONFIRMED).
- **The editing GhanaEd still requires is real but displaced** — corrupted
  indicators, placeholder references, blank metadata (CONFIRMED); teachers who
  "barely edit" are likely not checking those fields (POSSIBLE-UNCONFIRMED
  about actual teacher behaviour).
- SchemeKnit's fastest path to parity: items 2–6 above; its free-tier
  quota + provenance are already differentiators (CONFIRMED).

*Related: UX_FLOW.md · NETWORK_MAP.md · ARCHITECTURE_RECONSTRUCTION.md ·
DATA_MODEL_RECONSTRUCTION.md · GENERATION_FORENSICS.md ·
../GHANAED_FORENSIC_ANALYSIS.md*
