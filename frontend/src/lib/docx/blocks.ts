/**
 * Neutral block model -> `docx` Document.
 *
 * One function builds the Document; section renderers stay data-driven so the
 * content rules live on the server, not in a React page.
 */

import {
  AlignmentType,
  Document,
  HeadingLevel,
  PageBreak,
  PageOrientation,
  Packer,
  Paragraph,
  Table,
  TableCell,
  TableRow,
  TextRun,
  WidthType,
} from 'docx'
import type { DocxBlock, DocxRun, ExportDocument, ExportStructure, GridCell } from './types.ts'
import {
  A4_LANDSCAPE,
  A4_PORTRAIT,
  BODY_FONT,
  BODY_SIZE_HALF_POINTS,
  HEADING_COLOR,
  TABLE_BORDER,
} from './styles.ts'

const HEADING_LEVELS = [
  HeadingLevel.HEADING_1,
  HeadingLevel.HEADING_2,
  HeadingLevel.HEADING_3,
  HeadingLevel.HEADING_4,
  HeadingLevel.HEADING_5,
  HeadingLevel.HEADING_6,
]

function textRuns(runs: DocxRun[] | undefined): TextRun[] {
  return (runs || []).map(
    (run) => new TextRun({ text: run.text, bold: Boolean(run.bold), font: BODY_FONT }),
  )
}

function paragraphFromRuns(runs: DocxRun[] | undefined, bullet = false): Paragraph {
  const children = textRuns(runs)
  if (!children.length) children.push(new TextRun({ text: '', font: BODY_FONT }))
  return new Paragraph({
    children,
    ...(bullet ? { bullet: { level: 0 } } : {}),
    spacing: { after: 80 },
  })
}

function cellParagraphs(cell: GridCell): Paragraph[] {
  const paragraphs: Paragraph[] = []
  if (cell.runs && cell.runs.length) {
    paragraphs.push(
      new Paragraph({ children: textRuns(cell.runs), spacing: { after: 0 } }),
    )
    return paragraphs
  }
  const text = cell.text ?? ''
  const lines = text.split('\n')
  for (const line of lines) {
    paragraphs.push(
      new Paragraph({
        children: [new TextRun({ text: line, bold: Boolean(cell.bold), font: BODY_FONT })],
        spacing: { after: 0 },
      }),
    )
  }
  return paragraphs.length ? paragraphs : [new Paragraph({})]
}

function gridTable(block: Extract<DocxBlock, { kind: 'table' | 'customTable' }>): Table {
  const rows: TableRow[] = []
  for (let r = 0; r < block.rows; r += 1) {
    const cells = block.cells
      .filter((cell) => cell.r === r)
      .sort((a, b) => a.c - b.c)
    rows.push(
      new TableRow({
        children: cells.map((cell) => new TableCell({
          children: cellParagraphs(cell),
          columnSpan: cell.colspan && cell.colspan > 1 ? cell.colspan : undefined,
          rowSpan: cell.rowspan && cell.rowspan > 1 ? cell.rowspan : undefined,
        })),
      }),
    )
  }
  return new Table({
    rows,
    width: { size: 100, type: WidthType.PERCENTAGE },
    borders: TABLE_BORDER,
  })
}

export function blockToDocx(block: DocxBlock): Paragraph | Table {
  switch (block.kind) {
    case 'heading':
      return new Paragraph({
        heading: HEADING_LEVELS[Math.min(Math.max(block.level, 1), 6) - 1],
        alignment: block.align === 'center' ? AlignmentType.CENTER : AlignmentType.LEFT,
        children: [
          new TextRun({
            text: block.text,
            bold: true,
            color: HEADING_COLOR,
            font: BODY_FONT,
          }),
        ],
        spacing: { before: 120, after: 80 },
      })
    case 'paragraph':
      return paragraphFromRuns(block.runs, block.style === 'List Bullet')
    case 'table':
    case 'customTable':
      return gridTable(block)
    case 'pageBreak':
      return new Paragraph({ children: [new PageBreak()] })
    default:
      return new Paragraph({})
  }
}

export function buildBlocksDocument(
  documents: ExportDocument[],
  structure?: ExportStructure,
): Document {
  const children: (Paragraph | Table)[] = []
  for (const document of documents) {
    for (const block of document.blocks || []) {
      children.push(blockToDocx(block))
    }
  }
  if (!children.length) children.push(new Paragraph({}))

  const landscape = structure?.layout?.orientation === 'landscape'
  const page = landscape
    ? { size: { orientation: PageOrientation.LANDSCAPE, ...A4_LANDSCAPE } }
    : { size: { ...A4_PORTRAIT } }

  return new Document({
    styles: {
      default: {
        document: {
          run: { font: BODY_FONT, size: BODY_SIZE_HALF_POINTS },
          paragraph: { spacing: { after: 80 } },
        },
      },
    },
    sections: [{ properties: { page }, children }],
  })
}

/** Serialize a neutral block document to a browser Blob. */
export async function packBlocksDocument(
  documents: ExportDocument[],
  structure?: ExportStructure,
): Promise<Blob> {
  return Packer.toBlob(buildBlocksDocument(documents, structure))
}
