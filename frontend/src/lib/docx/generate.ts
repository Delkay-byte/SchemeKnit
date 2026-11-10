/**
 * DOCX/ZIP export orchestration.
 *
 * Runs in the page or in a Web Worker (same module, no DOM dependency except
 * fetch/Blob, both available in workers). One export at a time per job+format
 * so a double-click cannot build the same file twice.
 */

import { zipSync } from 'fflate'
import { loadTemplateAsset } from './assets.ts'
import { packBlocksDocument } from './blocks.ts'
import { safeDocxFilename, safeZipFilename, uniqueNames } from './filename.ts'
import { fillFormDocument } from './ooxml.ts'
import { DOCX_MIME } from './styles.ts'
import type {
  ExportModel,
  ExportOptions,
  ExportProgress,
  GeneratedFile,
} from './types.ts'

function assertActive(signal?: AbortSignal): void {
  if (signal?.aborted) {
    const error = new Error('Export cancelled.')
    error.name = 'AbortError'
    throw error
  }
}

function report(options: ExportOptions, progress: ExportProgress): void {
  options.onProgress?.(progress)
}

function documentForm(model: ExportModel, index: number) {
  const document = model.documents[index]
  if (!document?.form) throw new Error('The export model has no form data.')
  return document.form
}

async function renderSingleForm(model: ExportModel, options: ExportOptions) {
  const forms = model.documents.map((_, index) => documentForm(model, index))
  const assets = Array.from(new Set(forms.map((form) => form.asset)))
  if (assets.length > 1) {
    throw new Error('A combined Word document cannot mix template files.')
  }
  const bytes = await loadTemplateAsset(assets[0])
  assertActive(options.signal)
  report(options, {
    phase: 'rendering',
    completed: 0,
    total: model.documents.length,
    detail: 'Filling the approved Word form',
  })
  const filled = fillFormDocument(bytes, forms, { appendices: model.appendices })
  report(options, {
    phase: 'rendering',
    completed: model.documents.length,
    total: model.documents.length,
  })
  return filled
}

/** Build one .docx for the whole job (combined pages). */
export async function buildSingleDocx(
  model: ExportModel,
  options: ExportOptions = {},
): Promise<Uint8Array> {
  if (model.renderer === 'form') return renderSingleForm(model, options)
  const blob = await packBlocksDocument(model.documents, model.structure)
  report(options, {
    phase: 'rendering',
    completed: model.documents.length,
    total: model.documents.length,
  })
  return new Uint8Array(await blob.arrayBuffer())
}

/** Build one standalone .docx per lesson (for ZIP members). */
export async function buildLessonDocx(
  model: ExportModel,
  index: number,
  options: ExportOptions = {},
): Promise<Uint8Array> {
  assertActive(options.signal)
  const document = model.documents[index]
  if (!document) throw new Error('That lesson is not part of this export.')
  if (model.renderer === 'form' && document.form) {
    const bytes = await loadTemplateAsset(document.form.asset)
    assertActive(options.signal)
    return fillFormDocument(bytes, [document.form], {
      standalone: true,
      appendices: document.appendix ? [document.appendix] : [],
    })
  }
  const blob = await packBlocksDocument([document], model.structure)
  return new Uint8Array(await blob.arrayBuffer())
}

export async function generateDocx(
  model: ExportModel,
  options: ExportOptions = {},
): Promise<GeneratedFile> {
  report(options, { phase: 'preparing', completed: 0, total: model.lesson_count })
  assertActive(options.signal)
  const bytes = await buildSingleDocx(model, options)
  report(options, {
    phase: 'complete',
    completed: model.lesson_count,
    total: model.lesson_count,
  })
  const filename = safeDocxFilename(options.filename || model.filename)
  return { blob: new Blob([bytes.buffer as ArrayBuffer], { type: DOCX_MIME }), filename }
}

export async function generateZip(
  model: ExportModel,
  options: ExportOptions = {},
): Promise<GeneratedFile> {
  const total = model.documents.length
  if (!total) throw new Error('There is nothing to export.')
  report(options, { phase: 'preparing', completed: 0, total })

  const names = uniqueNames(model.documents.map((document, index) =>
    document.filename || `lesson_${index + 1}.docx`,
  ))
  const entries: Record<string, Uint8Array> = {}

  for (let index = 0; index < total; index += 1) {
    assertActive(options.signal)
    report(options, {
      phase: 'rendering',
      completed: index,
      total,
      detail: `Building ${names[index]}`,
    })
    // Sequential: one lesson in memory at a time keeps peak usage bounded.
    entries[names[index]] = await buildLessonDocx(model, index, options)
  }

  assertActive(options.signal)
  report(options, { phase: 'zipping', completed: total, total })
  const archive = zipSync(entries, { level: 6 })
  report(options, { phase: 'complete', completed: total, total })

  const fallback = model.filename.replace(/\.docx$/i, '.zip')
  return {
    blob: new Blob([archive.buffer as ArrayBuffer], { type: 'application/zip' }),
    filename: safeZipFilename(options.filename || fallback),
  }
}

// ── Duplicate-submit guard ────────────────────────────────────────────────────

const active = new Map<string, Promise<GeneratedFile>>()

export function exportKey(jobId: string | null, format: 'docx' | 'zip'): string {
  return `${jobId || 'unknown'}:${format}`
}

/**
 * Run one export, reusing an identical in-flight export.
 *
 * A double-click returns the same promise instead of building the document
 * twice; the caller still receives the one result.
 */
export function runOnce(
  key: string,
  task: () => Promise<GeneratedFile>,
): Promise<GeneratedFile> {
  const running = active.get(key)
  if (running) return running
  const promise = task().finally(() => {
    if (active.get(key) === promise) active.delete(key)
  })
  active.set(key, promise)
  return promise
}

export function isExportRunning(key: string): boolean {
  return active.has(key)
}
