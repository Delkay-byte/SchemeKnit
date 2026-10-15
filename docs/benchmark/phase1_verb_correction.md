# Phase 1 — P4 Measurable-Verb Correction (Frozen Benchmark Rerun, Oct 2026)

**Change:** the canonical rubric (`src/curriculum/lesson_rubric.py`) and the
runtime P4 gate previously decided "does this objective name a measurable
action?" with `any(v in obj.lower() for v in _MEASURABLE_VERBS)` — a stale,
competing verb inventory matched by SUBSTRING. Legitimate measurable lead
verbs on the official curriculum (`add`, `multiply`, `install`, `indicate`,
`assess`, `relate`, `recognise`, `skip count`, French `lire`/`écouter`, …)
were absent, so their verb-led objectives hard-failed as
`generic_objective`; conversely, accidental substrings (`household` → `use`,
`performance` → `perform`) could pass.

**Fix:** ONE shared, structured indicator-action interpretation
(`src/curriculum/indicator_actions.py` — per-category action phrases,
longest-first word-boundary matching, `learners can/will` preamble stripping,
accented/French phrases as first-class members). The rubric's
`_MEASURABLE_VERBS` is now an alias of the shared canon and reads the
objective's OUTCOME verb (the action directly after the "Learners …" marker),
so a measurable word elsewhere in the sentence can never rescue a weak
outcome. **No thresholds lowered, no floors changed, no failing cases
removed; the recall floor (≥ 0.15) and all other hard-failure criteria are
untouched.**

## Frozen corpora — before vs after (AI OFF, Zeli OFF, thresholds unchanged)

| Corpus | Before (frozen) | After this correction | Δ |
|---|---|---|---|
| 11-lesson core (`benchmark_deterministic_lessons.py`) | 11/11 ready, 0 hard failures | 11/11 ready, 0 hard failures (all totals unchanged) | no change |
| 40-lesson expanded (`benchmark_hardening.py`) | 31/40 ready (0.775), 7 × `generic_objective` | **40/40 ready (1.0)**, 0 hard failures | +9 lessons |
| 19-lesson messy (`benchmark_hardening.py`) | 12/19 ready (0.632), 7 × `generic_objective` | **19/19 ready (1.0)**, 0 hard failures | +7 lessons |

Previously false-rejected cases now correctly accepted (all hard-failed
`generic_objective` before):

- `B7.1.1.1.1 Add whole numbers up to 10,000` (Mathematics)
- `B7.1.1.2.1 Multiply two-digit numbers by two-digit numbers` (Mathematics)
- `B7.1.1.2 Install an operating system.` (ICT)
- `B6.1.4.1.1 : Indicate the similarities and differences between folktales
  and stories` (Ghanaian Language)
- `B6.1.3.1.1 : Relate the central messages of poems to personal
  experiences.` (English) — in both corpora
- `B6.6.1.1.1 : Recognise topics for magazine` (Ghanaian Language)
- `B6.1.1.1.6 : Skip count forwards and backwards in 5,000s, 10,000s …`
  (Mathematics)
- `B6.3.4.1.1 Assess the changes that the European presence brought to
  Ghana` (History) — in both corpora
- `B6.1.3.3.1 / B6.1.4.3.1 Lire et comprendre …` and
  `B6.1.1.1.x Écouter/Regarder …` (French rows, accented source text)

Cases still rejected (negative tests, and they remain failing):

- "learners will discuss the topic" / "Learners can explore the topic" /
  "Learners can learn about …" — generic lead or sub-floor indicator recall.
- noun-phrase outcomes ("Learners can operating systems and devices").
- measurable word only embedded mid-sentence ("… the uses of each
  component") — outcome slot must name the action.

## Regression detection of genuinely weak objectives

Weak-objective rejection was re-verified, not weakened:
`tests/test_phase1_measurable_verbs.py` pins the chain (FULL indicator →
deterministic objective → rubric → P4 gate) for all ten affected cases and
the negative cases above; the P2.1/P4 suites (169 tests) and the broader
quality/export/wapef/quota/autopilot slice (776 tests) stayed green.

## Committed artifact provenance

- Interpretation canon: `backend/src/curriculum/indicator_actions.py`
- Rubric rewiring: `backend/src/curriculum/lesson_rubric.py`
- Chain + negative tests: `backend/tests/test_phase1_measurable_verbs.py`
- Frozen baselines `docs/benchmark/*.json` were NOT rewritten; rerun outputs
  recorded in this note only.
