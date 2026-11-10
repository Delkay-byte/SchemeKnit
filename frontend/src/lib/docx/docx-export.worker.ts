/// <reference lib="webworker" />

/**
 * DOCX export Web Worker.
 *
 * Keeps OOXML construction, DEFLATE compression and ZIP packaging off the
 * teacher's main thread. Progress is streamed back per document so the page can
 * show real movement instead of a frozen spinner.
 */

import { generateDocx, generateZip } from './generate.ts'
import type { ExportModel, ExportProgress } from './types.ts'

type Request = {
  id: string
  format: 'docx' | 'zip'
  model: ExportModel
}

type Reply =
  | { id: string; type: 'progress'; progress: ExportProgress }
  | { id: string; type: 'done'; buffer: ArrayBuffer; filename: string; mime: string }
  | { id: string; type: 'error'; message: string; name?: string }

const scope = self as unknown as DedicatedWorkerGlobalScope

scope.onmessage = async (event: MessageEvent<Request>) => {
  const { id, format, model } = event.data
  const onProgress = (progress: ExportProgress) => {
    const reply: Reply = { id, type: 'progress', progress }
    scope.postMessage(reply)
  }
  try {
    const file = format === 'zip'
      ? await generateZip(model, { onProgress })
      : await generateDocx(model, { onProgress })
    const buffer = await file.blob.arrayBuffer()
    const reply: Reply = {
      id,
      type: 'done',
      buffer,
      filename: file.filename,
      mime: file.blob.type,
    }
    scope.postMessage(reply, [buffer])
  } catch (error) {
    const reply: Reply = {
      id,
      type: 'error',
      message: error instanceof Error ? error.message : 'Document generation failed.',
      name: error instanceof Error ? error.name : undefined,
    }
    scope.postMessage(reply)
  }
}
