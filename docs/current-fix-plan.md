# Current fix plan

## Root causes
- Config: full PUT payload with `{}` fallbacks overwrites saved `schemes.lesson_config`; frontend save handler dropped WAPEF/competency fields.
- Zeli quality: prompt and validators omit worked examples, questions, answers, marking guidance, duration truth, rural guidance, voice and sub-strand cap.
- Voice: provider third-person teacher actions pass verbatim into stored plans and DOCX.
- Test labels: production QA upload renamed a genuine scheme file; UI echoed raw `scheme.filename`. No literal `eKnit` in source.

## Sequence
1. [x] Confirm baseline `07eb97f`, live Render on same commit.
2. [x] Trace config, Zeli, UI root causes.
3. [x] Add failing tests: config snapshot preservation, AI allowlist, WAPEF annual immutability, voice/quality, copy.
4. [x] Implement backend config merge and AI boundary.
5. [x] Implement frontend full-snapshot save/restore.
6. [x] Wire Zeli quality guard, prompt/schema contract, cross-indicator duplicate gate.
7. [x] Fix generate/review copy to use real subject/class/term.
8. [x] Keep production QA artefacts intact; no production DB mutation without live verification.
9. [x] Run focused backend + frontend tests; inspect representative DOCX output.
10. [ ] Confirm broader backend suite result.
11. [ ] One commit, one push to `main`, one CI run, Render auto-deploy only.
12. [ ] Final report with mandated headings only.

## Safety
- No reset, discard, force-push, destructive cleanup or MaaCash changes.
- Reference DOCX kept read-only.
- v057 is additive only: three JSON columns, no rewrite of existing rows.
- Production QA scheme `47c11efa-8bfe-4bdb-b4db-83f85f558575`, job `6a2db19d-0bed-43ca-9147-9d577fe395ef`, owner `Internal test account` remain untouched.
- Original QA upload filename: `PERFORMANCE TEST - BASIC 4 MATHEMATICS - POSTDEPLOY.docx`; export filename: `Term_1_Basic_4_Lesson_Plan_For_Mathematics.docx`.
