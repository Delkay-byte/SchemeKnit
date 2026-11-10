/**
 * Worker client with a main-thread fallback.
 *
 * The worker is preferred: it keeps Word serialization and ZIP compression off
 * the UI thread. If a Worker cannot be constructed (older embedded webview,
 * strict CSP), the same code runs on the main thread so export still works.
 */

import { generateDocx, generateZip, exportKey, runOnce } from './generate.ts'
import type { ExportModel, ExportOptions, ExportProgress, GeneratedFile } from './types.ts'

interface WorkerReply {
  id: string
  type: 'progress' | 'done' | 'error'
  progress?: ExportProgress
  buffer?: ArrayBuffer
  filename?: string
  mime?: string
  message?: string
  name?: string
}

let worker: Worker | null = null
let workerBroken = false
let sequence = 0
const pending = new Map<string, {
  resolve: (file: GeneratedFile) => void
  reject: (error: Error) => void
  options: ExportOptions
}>()

function getWorker(): Worker | null {
  if (workerBroken || typeof Worker === 'undefined') return null
  if (worker) return worker
  try {
    worker = new Worker(new URL('./docx-export.worker.ts', import.meta.url), {
      type: 'module',
    })
    worker.onmessage = (event: MessageEvent<WorkerReply>) => {
      const reply = event.data
      const entry = pending.get(reply.id)
      if (!entry) return
      if (reply.type === 'progress' && reply.progress) {
        entry.options.onProgress?.(reply.progress)
        return
      }
      pending.delete(reply.id)
      if (reply.type === 'done' && reply.buffer) {
        entry.resolve({
          blob: new Blob([reply.buffer], { type: reply.mime || 'application/octet-stream' }),
          filename: reply.filename || 'download',
        })
      } else {
        const error = new Error(reply.message || 'Document generation failed.')
        if (reply.name) error.name = reply.name
        entry.reject(error)
      }
    }
    worker.onerror = (event) => {
      workerBroken = true
      const error = new Error(event.message || 'The document worker stopped unexpectedly.')
      for (const entry of pending.values()) entry.reject(error)
      pending.clear()
      worker?.terminate()
      worker = null
    }
  } catch {
    workerBroken = true
    worker = null
  }
  return worker
}

async function viaWorker(
  model: ExportModel,
  format: 'docx' | 'zip',
  options: ExportOptions,
): Promise<GeneratedFile | null> {
  const target = getWorker()
  if (!target) return null
  const id = `export-${++sequence}`
  return new Promise<GeneratedFile>((resolve, reject) => {
    pending.set(id, { resolve, reject, options })
    const onAbort = () => {
      pending.delete(id)
      // A terminated worker cannot cancel a single job; terminate and rebuild
      // on the next export so an aborted job leaves no CPU work behind.
      target.terminate()
      worker = null
      const error = new Error('Export cancelled.')
      error.name = 'AbortError'
      reject(error)
    }
    options.signal?.addEventListener('abort', onAbort, { once: true })
    if (options.signal?.aborted) {
      onAbort()
      return
    }
    target.postMessage({ id, format, model })
  })
}

/** Run the export on the worker when available, otherwise on the main thread. */
export async function runExport(
  model: ExportModel,
  format: 'docx' | 'zip',
  options: ExportOptions = {},
): Promise<GeneratedFile> {
  if (typeof window === 'undefined') {
    return format === 'zip'
      ? generateZip(model, options)
      : generateDocx(model, options)
  }
  const workerResult = await viaWorker(model, format, options).catch((error) => {
    if (error?.name === 'AbortError') throw error
    return null
  })
  if (workerResult) return workerResult
  return format === 'zip'
    ? generateZip(model, options)
    : generateDocx(model, options)
}

/**
 * Public entry point: one in-flight export per job+format.
 * Calling twice with the same key returns the first promise.
 */
export function exportLessonPlans(
  model: ExportModel,
  format: 'docx' | 'zip',
  options: ExportOptions = {},
): Promise<GeneratedFile> {
  return runOnce(exportKey(model.job_id, format), () => runExport(model, format, options))
}
