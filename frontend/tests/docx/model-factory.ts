import type { ExportModel } from '../../src/lib/docx/types.ts'

/** Minimal valid model used by ZIP/duplicate tests (blocks renderer). */
export function modelWithTwoPlans(): ExportModel {
  return {
    schema_version: 1,
    job_id: 'job-test',
    filename: 'Lesson_Plans_Scheme.docx',
    lesson_count: 2,
    template: { id: 'tpl-jhs-ges', name: 'GES-Style (JHS)' },
    render_context: { term: 'Term 1' },
    renderer: 'blocks',
    documents: [
      {
        lesson_id: 'a',
        week_number: 1,
        lesson_sequence: 1,
        filename: 'SCIENCE_B7_W01_L01_2026-02-03.docx',
        first: true,
        blocks: [
          { kind: 'heading', level: 1, text: 'LESSON PLAN', align: 'center' },
          { kind: 'paragraph', runs: [{ text: 'Week 1 lesson 1', bold: false }] },
          { kind: 'pageBreak' },
        ],
      },
      {
        lesson_id: 'b',
        week_number: 1,
        lesson_sequence: 2,
        filename: 'SCIENCE_B7_W01_L02_2026-02-03.docx',
        first: false,
        blocks: [
          { kind: 'heading', level: 1, text: 'LESSON PLAN', align: 'center' },
          { kind: 'paragraph', runs: [{ text: 'Week 1 lesson 2', bold: false }] },
          { kind: 'pageBreak' },
        ],
      },
    ],
  }
}
