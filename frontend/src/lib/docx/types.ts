/**
 * Browser DOCX export model (server-produced, client-serialized).
 *
 * The backend owns every content decision. This module only describes the
 * neutral shape the browser turns into OOXML.
 */

export interface DocxRun {
  text: string
  bold?: boolean
}

export interface HeadingBlock {
  kind: 'heading'
  text: string
  level: 1 | 2 | 3 | 4 | 5 | 6
  align?: 'left' | 'center'
}

export interface ParagraphBlock {
  kind: 'paragraph'
  runs: DocxRun[]
  style?: string | null
}

export interface GridCell {
  r: number
  c: number
  /** Plain text form (built-in section tables). */
  text?: string
  bold?: boolean
  /** Rich form (custom template cells: bold label + normal value). */
  runs?: DocxRun[]
  colspan?: number
  rowspan?: number
}

export interface TableBlock {
  kind: 'table' | 'customTable'
  style?: string
  rows: number
  cols: number
  cells: GridCell[]
}

export interface PageBreakBlock {
  kind: 'pageBreak'
}

export type DocxBlock =
  | HeadingBlock
  | ParagraphBlock
  | TableBlock
  | PageBreakBlock

export interface GridFill {
  table: number
  row: number
  column: number
  text: string
}

export interface FormPlan {
  kind: 'official_ges' | 'wapef'
  /** Public path of the bundled placeholder form, e.g. docx-templates/x.docx */
  asset: string
  tokens: Record<string, string>
  grid_fills: GridFill[]
  /** Header lines for the combined document (first page carries identity). */
  header_lines: string[]
  /** Header lines when this document is downloaded on its own. */
  standalone_header_lines: string[]
  first: boolean
  strip_guidance: boolean
  title_pattern: string | null
}

export interface AppendixBlock {
  text: string
  bold: boolean
  page_break_before: boolean
}

export interface ExportDocument {
  lesson_id: string | null
  week_number: number | null
  lesson_sequence: number | null
  filename: string
  first: boolean
  blocks?: DocxBlock[]
  form?: FormPlan
  appendix?: AppendixBlock[]
}

export interface StructureLayout {
  orientation?: 'portrait' | 'landscape'
}

export interface ExportStructure {
  layout?: StructureLayout
  tables?: unknown[]
  meta?: Record<string, unknown>
}

export interface ExportModel {
  schema_version: number
  job_id: string | null
  filename: string
  lesson_count: number
  template: { id: string | null; name: string | null }
  render_context: Record<string, unknown>
  renderer: 'form' | 'blocks'
  structure?: ExportStructure
  documents: ExportDocument[]
  appendices?: AppendixBlock[][]
}

export type ExportPhase =
  | 'preparing'
  | 'rendering'
  | 'zipping'
  | 'complete'

export interface ExportProgress {
  phase: ExportPhase
  completed: number
  total: number
  detail?: string
}

export interface ExportOptions {
  signal?: AbortSignal
  onProgress?: (progress: ExportProgress) => void
  /** Override the server-provided ZIP member name. */
  filename?: string
}

export interface GeneratedFile {
  blob: Blob
  filename: string
}
