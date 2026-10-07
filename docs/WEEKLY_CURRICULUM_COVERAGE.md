# Weekly Curriculum Coverage — Source-Occurrence Rule

**Status:** Authoritative (Priority 1, 2026-10-07)
**Applies to:** allocation engine, coverage validation, allocation preview,
generation requests, lesson persistence, exports.

## The rule

> **Curriculum lesson coverage follows source occurrences in the teacher's
> scheme. Teaching periods describe timetable context and do not cap, defer,
> or move lesson-plan occurrences between curriculum weeks.**

> **Repeated indicator codes across different source weeks are legitimate
> distinct occurrences unless they refer to the exact same source occurrence.**

The fundamental relationship is:

```
SOURCE OCCURRENCE  →  WEEKLY LESSON PLAN
```

Not:

```
INDICATOR → TIMETABLE CAPACITY → AVAILABLE LESSON SLOTS → POSSIBLE CARRY-FORWARD
```

Teaching periods (`1st period`, `2 & 4`, `Monday`, `2 periods`, `duration`)
are metadata describing the school's timetable. They are **not** a cap on how
many curriculum lesson plans must exist. The teacher/school decides how the
teaching is practically handled; SchemeKnit's job is to produce the lesson
plans covering the curriculum occurrences assigned to each week.

## Canonical model

**A. Source occurrence** — a curriculum occurrence extracted from the
teacher's scheme. Preserved fields: `scheme_id`, source week, occurrence
identity, indicator code, full indicator text, content standard, strand,
sub-strand, provenance, teaching-period metadata when present, review status.

**B. Lesson-plan occurrence** — the generated lesson for one source
occurrence. It preserves source week, source occurrence identity, indicator,
curriculum context and provenance.

**C. Teaching timetable** — descriptive metadata about when/how the teacher
may teach. Never determines how many lesson plans are created.

## Allocation rule

For each instructional source occurrence, create **exactly one** lesson-plan
occurrence, in the source occurrence's week (`source week 5 → lesson week 5`).
The system must not:

- roll an occurrence forward to a later week,
- "continue in the next teaching week",
- consume the next week's teaching capacity,
- rebalance indicators across weeks,
- optimise the scheme against timetable availability.

### Valid cases (no carry-forward in any of them)

| Case | Teaching periods | Indicators | Result |
|------|------------------|------------|--------|
| A | 2 | 2 | 2 lesson plans |
| B | 2 | 3 | 3 lesson plans |
| C | 2 | 4 | 4 lesson plans |
| D | 1 | 4 | 4 lesson plans |
| E | 0 / unspecified | 3 | 3 lesson plans |
| F | 4 | 1 | 1 lesson plan |

If teaching-period information is incomplete or unavailable, the lesson plan
still belongs to its source week. The UI may show *"Teaching periods not
specified"* as context; this never blocks curriculum lesson generation.

## Generation count and quota

The number of instructional lesson occurrences for a week equals the number of
source instructional occurrences in that week. Never
`min(indicators, available_periods)`, never `indicators − available_periods`,
never "overflow" indicators for later weeks.

The **Free Tier quota is a commercial generation limit**; the
**teaching-period count is not a generation limit**. The full weekly
occurrence list is always shown; the existing quota policy applies to the
selected generation set only.

## Repeated indicators and duplicates

- The same indicator code in two different source weeks is **two** legitimate
  occurrences → two lesson plans, one per week, no duplicate-allocation error.
- Duplicate detection keys on the **source occurrence identity**
  (`week<source_week>:<position_in_week>:<indicator_code>`), never on
  `indicator_code` alone.
- The same source occurrence assigned/generated more than once is still
  caught: identical (code, text) entries inside one source week collapse to a
  single occurrence at parse/allocation time (Defect D5 protection, unchanged).

## Special, revision and mixed weeks

- Instructional occurrences in a **mixed week** stay in that week; the
  special-period segment remains separate metadata and teaching-period
  information stays descriptive.
- A **special-only week** with no instructional source occurrences generates
  no lesson plan (nothing is invented).
- An **instructional week with incomplete timetable information** generates
  its lesson occurrences anyway.

## Source-week integrity

For every generated lesson: `lesson.week_number == source_occurrence.week_number`
and `lesson.teaching_week == lesson.week_number`. Source week, week-ending
date, source occurrence identity, indicator code and provenance are preserved
through: allocation → generation request → lesson persistence → reload →
export. There is one week source of truth: the source occurrence's week.

## API / data contract

Explicit concepts (preferred over "slot" identity):

- `source_occurrence_id` — canonical occurrence identity (allocation rows,
  preview rows, provenance, serialized lessons, `lesson_plans` column since
  migration `v032_source_occurrence_id`).
- `source_week` — the curriculum week (allocation `week_number`).
- `teaching_week` — always equal to `source_week` for new lessons; the field
  remains for contract stability.
- `carry_forward` / `carry_forward_from_week` — legacy fields; the current
  engine always sets them false.
- `teaching_period`, `teaching_period_label`, `period_index` — timetable
  context / lesson ordinal within the week, never a generation cap.

Migration `v032_source_occurrence_id` is additive and idempotent; existing
rows keep an empty identity and stay valid.

## Required regression tests

`backend/tests/test_weekly_coverage_semantics.py` covers the mandated matrix
T1–T14 (capacity cases A–F, repeated indicators across weeks, same-source
duplicate protection, mixed and special-only weeks, week order, generation
request identity, persistence/reload, quota separation, cross-week isolation,
and the v032 migration).
