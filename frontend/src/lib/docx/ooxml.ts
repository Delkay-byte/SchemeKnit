/**
 * In-place OOXML form filler.
 *
 * The bundled GES/WAPEF forms are approved .docx documents. Rebuilding them
 * with a layout library would create a second, drifting layout, so the browser
 * edits the template's own `word/document.xml`: it fills bracketed tokens,
 * fills the declared delivery-grid cells and clones the form block once per
 * lesson, exactly as the server renderer does.
 *
 * All text comes from the server model. This module performs no curriculum
 * decisions.
 */

import { strFromU8, strToU8, unzipSync, zipSync } from 'fflate'
import type { FormPlan } from './types.ts'

const W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

export interface XmlAdapter {
  parse(xml: string): Document
  serialize(doc: Document): string
}

function browserXml(): XmlAdapter {
  return {
    parse: (xml) => new DOMParser().parseFromString(xml, 'application/xml'),
    serialize: (doc) => new XMLSerializer().serializeToString(doc),
  }
}

function elements(parent: Element | Document, localName: string): Element[] {
  return Array.from(parent.getElementsByTagNameNS(W_NS, localName))
}

function directChildren(parent: Element, localName: string): Element[] {
  const out: Element[] = []
  for (let i = 0; i < parent.childNodes.length; i += 1) {
    const node = parent.childNodes.item(i)
    if (node && node.nodeType === 1 && (node as Element).localName === localName) {
      out.push(node as Element)
    }
  }
  return out
}

function paragraphText(paragraph: Element): string {
  let text = ''
  const walk = (node: Node) => {
    for (let i = 0; i < node.childNodes.length; i += 1) {
      const child = node.childNodes.item(i)
      if (!child) continue
      if (child.nodeType === 1) {
        const element = child as Element
        if (element.localName === 't') {
          text += element.textContent || ''
        } else if (element.localName === 'br') {
          text += '\n'
        } else if (element.localName === 'tab') {
          text += '\t'
        } else {
          walk(element)
        }
      }
    }
  }
  walk(paragraph)
  return text
}

function makeEl(doc: Document, name: string): Element {
  return doc.createElementNS(W_NS, `w:${name}`)
}

function makeText(doc: Document, text: string): Element {
  const node = makeEl(doc, 't')
  node.setAttribute('xml:space', 'preserve')
  node.textContent = text
  return node
}

function makeRun(doc: Document, text: string): Element {
  const run = makeEl(doc, 'r')
  run.appendChild(makeText(doc, text))
  return run
}

/**
 * Replace a paragraph's runs with `text`, keeping the first run's formatting.
 * Newlines become real Word line breaks (`w:br`).
 */
function fillParagraph(doc: Document, paragraph: Element, text: string): void {
  const runs = elements(paragraph, 'r')
  let first = runs[0]
  if (!first) {
    first = makeRun(doc, '')
    const pPr = directChildren(paragraph, 'pPr')[0]
    if (pPr) paragraph.insertBefore(first, pPr.nextSibling)
    else paragraph.insertBefore(first, paragraph.firstChild)
  }
  for (const extra of runs.slice(1)) {
    extra.parentNode?.removeChild(extra)
  }
  for (let i = first.childNodes.length - 1; i >= 0; i -= 1) {
    const child = first.childNodes.item(i)
    if (child && !(child.nodeType === 1 && (child as Element).localName === 'rPr')) {
      first.removeChild(child)
    }
  }
  const segments = (text || '').split('\n')
  segments.forEach((segment, index) => {
    if (index > 0) first.appendChild(makeEl(doc, 'br'))
    first.appendChild(makeText(doc, segment))
  })
}

function fillCell(doc: Document, cell: Element, text: string): void {
  const paragraphs = directChildren(cell, 'p')
  if (!paragraphs.length) {
    const paragraph = makeEl(doc, 'p')
    cell.appendChild(paragraph)
    fillParagraph(doc, paragraph, text)
    return
  }
  fillParagraph(doc, paragraphs[0], text)
  for (const extra of paragraphs.slice(1)) {
    extra.parentNode?.removeChild(extra)
  }
}

function pageBreakParagraph(doc: Document): Element {
  const paragraph = makeEl(doc, 'p')
  const run = makeEl(doc, 'r')
  const br = makeEl(doc, 'br')
  br.setAttributeNS(W_NS, 'w:type', 'page')
  run.appendChild(br)
  paragraph.appendChild(run)
  return paragraph
}

/** Append the server-authored assessment structure with plain OOXML runs. */
function appendAppendix(doc: Document, body: Element, sectPr: Element | null,
  blocks: import('./types').AppendixBlock[]): void {
  for (const block of blocks || []) {
    const paragraph = makeEl(doc, 'p')
    if (block.page_break_before) {
      const pPr = makeEl(doc, 'pPr')
      pPr.appendChild(makeEl(doc, 'pageBreakBefore'))
      paragraph.appendChild(pPr)
    }
    const run = makeEl(doc, 'r')
    if (block.bold) {
      const rPr = makeEl(doc, 'rPr')
      rPr.appendChild(makeEl(doc, 'b'))
      run.appendChild(rPr)
    }
    run.appendChild(makeText(doc, block.text || ''))
    paragraph.appendChild(run)
    if (sectPr) body.insertBefore(paragraph, sectPr)
    else body.appendChild(paragraph)
  }
}

function topLevelParagraphs(roots: Element[]): Element[] {
  return roots.filter((node) => node.localName === 'p')
}

function paragraphsWithin(roots: Element[]): Element[] {
  const out: Element[] = []
  for (const root of roots) {
    if (root.localName === 'p') out.push(root)
    out.push(...elements(root, 'p'))
  }
  return out
}

function tablesWithin(roots: Element[]): Element[] {
  const out: Element[] = []
  for (const root of roots) {
    if (root.localName === 'tbl') out.push(root)
    out.push(...elements(root, 'tbl'))
  }
  return out
}

function applyHeader(doc: Document, roots: Element[], plan: FormPlan,
  lines: string[], standalone: boolean): void {
  if (!lines.length) return
  if (plan.kind === 'wapef' && !standalone && !plan.first) {
    // The server renderer always writes the two positional WAPEF header
    // paragraphs on the first page only; cloned pages keep their blank header.
    return
  }
  const bodyParagraphs = topLevelParagraphs(roots)
  if (plan.kind === 'wapef') {
    if (bodyParagraphs[0]) fillParagraph(doc, bodyParagraphs[0], lines[0] || '')
    if (bodyParagraphs[1]) fillParagraph(doc, bodyParagraphs[1], lines[1] || '')
    return
  }
  if (!plan.title_pattern) return
  const pattern = new RegExp(plan.title_pattern, 'is')
  for (const paragraph of bodyParagraphs) {
    if (pattern.test(paragraphText(paragraph))) {
      fillParagraph(doc, paragraph, lines.join('\n'))
      return
    }
  }
}

function fillPlan(doc: Document, roots: Element[], plan: FormPlan,
  standalone: boolean): void {
  const header = standalone ? plan.standalone_header_lines : plan.header_lines

  if (plan.strip_guidance) {
    const heading = /^\s*\d+\.\s+[A-Z][A-Z \-/&]+$/
    for (const paragraph of topLevelParagraphs(roots)) {
      const text = paragraphText(paragraph).trim()
      if (!text) continue
      if (heading.test(text) || text.startsWith('Instructions for AI Engine:')) {
        paragraph.parentNode?.removeChild(paragraph)
      }
    }
  }

  const tokenPattern = /\[([A-Z][A-Z0-9_]*)\]/g
  for (const paragraph of paragraphsWithin(roots)) {
    const text = paragraphText(paragraph)
    tokenPattern.lastIndex = 0
    const tokens = Array.from(text.matchAll(tokenPattern)).map((m) => m[1])
    if (!tokens.length) continue
    const replacement = tokens
      .map((token) => plan.tokens[token] || '')
      .filter((value) => value !== '')
      .join('\n')
    fillParagraph(doc, paragraph, replacement)
  }

  const tables = tablesWithin(roots)
  for (const fill of plan.grid_fills || []) {
    const table = tables[fill.table]
    if (!table) continue
    const rows = directChildren(table, 'tr')
    const row = rows[fill.row]
    if (!row) continue
    const cells = directChildren(row, 'tc')
    const cell = cells[fill.column]
    if (!cell) continue
    fillCell(doc, cell, fill.text || '')
  }

  applyHeader(doc, roots, plan, header, standalone)

  const leftovers = paragraphsWithin(roots)
    .flatMap((paragraph) => Array.from(paragraphText(paragraph).matchAll(tokenPattern)))
    .map((match) => match[1])
  if (leftovers.length) {
    throw new Error(
      `The Word form still contains unfilled placeholders: ${Array.from(new Set(leftovers)).join(', ')}`,
    )
  }
}

export interface FillFormOptions {
  /** Fill the form for one standalone download: every file shows identity. */
  standalone?: boolean
  /** Server-authored assessment structure, appended after the forms. */
  appendices?: import('./types').AppendixBlock[][]
  xml?: XmlAdapter
}

/**
 * Fill one bundled form for every plan, cloning the form block per lesson.
 * Returns the complete .docx package as bytes.
 */
function styleWapefPagination(doc: Document): void {
  const tables = elements(doc, 'tbl')
  if (!tables.length || tables.length % 3 !== 0) return
  for (let start = 0; start < tables.length; start += 3) {
    for (const table of [tables[start + 1], tables[start + 2]]) {
      if (!table) continue
      const rows = directChildren(table, 'tr')
      if (!rows.length) continue
      // Repeat the delivery-grid header on every continuation page.
      const header = rows[0]
      const headerPr = directChildren(header, 'trPr')[0] || (() => {
        const pr = makeEl(doc, 'trPr')
        header.insertBefore(pr, header.firstChild)
        return pr
      })()
      if (!directChildren(headerPr, 'tblHeader').length) {
        headerPr.appendChild(makeEl(doc, 'tblHeader'))
      }
      for (let i = 1; i < rows.length; i += 1) {
        const row = rows[i]
        const textLength = directChildren(row, 'tc')
          .map((cell) => paragraphsWithin([cell]).map((p) => paragraphText(p)).join(''))
          .join('').length
        const rowPr = directChildren(row, 'trPr')[0] || (() => {
          const pr = makeEl(doc, 'trPr')
          row.insertBefore(pr, row.firstChild)
          return pr
        })()
        const split = directChildren(rowPr, 'cantSplit')[0]
        if (textLength < 2000 && !split) {
          rowPr.appendChild(makeEl(doc, 'cantSplit'))
        } else if (textLength >= 2000 && split) {
          rowPr.removeChild(split)
        }
      }
    }
  }
}

export function fillFormDocument(
  templateBytes: Uint8Array,
  plans: FormPlan[],
  options: FillFormOptions = {},
): Uint8Array {
  const xml = options.xml || browserXml()
  const files = unzipSync(templateBytes)
  const documentXml = files['word/document.xml']
  if (!documentXml) throw new Error('The Word form is missing word/document.xml')
  const doc = xml.parse(strFromU8(documentXml))
  if (doc.getElementsByTagName('parsererror').length) {
    throw new Error('The Word form could not be parsed')
  }
  const body = elements(doc, 'body')[0]
  if (!body) throw new Error('The Word form has no document body')
  const sectPr = directChildren(body, 'sectPr')[0] || null

  const roots = Array.from(body.childNodes)
    .filter((node): node is Element => node.nodeType === 1 && node !== sectPr)
    .filter((node) => node.localName !== 'sectPr')
  const snapshot = roots.map((node) => node.cloneNode(true) as Element)

  if (!plans.length) throw new Error('There is nothing to export')

  fillPlan(doc, roots, plans[0], Boolean(options.standalone))
  for (const plan of plans.slice(1)) {
    const breakParagraph = pageBreakParagraph(doc)
    if (sectPr) body.insertBefore(breakParagraph, sectPr)
    else body.appendChild(breakParagraph)
    const copies = snapshot.map((node) => node.cloneNode(true) as Element)
    for (const copy of copies) {
      if (sectPr) body.insertBefore(copy, sectPr)
      else body.appendChild(copy)
    }
    fillPlan(doc, copies, plan, Boolean(options.standalone))
  }

  for (const appendix of options.appendices || []) {
    appendAppendix(doc, body, sectPr, appendix || [])
  }

  if (plans[0]?.kind === 'wapef') styleWapefPagination(doc)

  files['word/document.xml'] = strToU8(xml.serialize(doc))
  return zipSync(files, { level: 6 })
}

/** Text extraction for regression fixtures and acceptance checks. */
export function extractDocxText(bytes: Uint8Array, xml?: XmlAdapter): string {
  const adapter = xml || browserXml()
  const files = unzipSync(bytes)
  const documentXml = files['word/document.xml']
  if (!documentXml) return ''
  const doc = adapter.parse(strFromU8(documentXml))
  const paragraphs = elements(doc, 'p')
  return paragraphs
    .map((paragraph) => paragraphText(paragraph))
    .filter((text) => text.trim())
    .join('\n')
}
