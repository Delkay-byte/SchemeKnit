/**
 * Centralised document constants for browser DOCX export.
 *
 * These mirror the backend python-docx renderer: Arial 11 pt body text and the
 * SchemeKnit navy heading colour (0, 51, 102).
 */

import { BorderStyle } from 'docx'

export const DOCX_MIME =
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

export const BODY_FONT = 'Arial'
export const BODY_SIZE_HALF_POINTS = 22 // 11 pt
export const HEADING_COLOR = '003366'

export const TABLE_BORDER = {
  top: { style: BorderStyle.SINGLE, size: 4, color: '000000' },
  bottom: { style: BorderStyle.SINGLE, size: 4, color: '000000' },
  left: { style: BorderStyle.SINGLE, size: 4, color: '000000' },
  right: { style: BorderStyle.SINGLE, size: 4, color: '000000' },
  insideHorizontal: { style: BorderStyle.SINGLE, size: 4, color: '000000' },
  insideVertical: { style: BorderStyle.SINGLE, size: 4, color: '000000' },
}

/** A4 in twips, used for custom-template page orientation. */
export const A4_PORTRAIT = { width: 11906, height: 16838 }
export const A4_LANDSCAPE = { width: 16838, height: 11906 }

export const LABELS = {
  tableOfContents: 'Contents',
} as const
