/** Safe filenames for browser-generated Word/ZIP downloads. */

const ILLEGAL = /[<>:"/\\|?*\u0000-\u001f]/g
const RESERVED = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\.|$)/i

/** Filesystem-safe, length-bounded name that keeps the DOCX extension. */
export function safeDocxFilename(name: string, fallback = 'lesson_plan.docx'): string {
  const base = (name || fallback).replace(/\.docx$/i, '')
  let cleaned = base
    .replace(ILLEGAL, '_')
    .replace(/\s+/g, ' ')
    .replace(/^\.+|\.+$/g, '')
    .trim()
  if (!cleaned) cleaned = fallback.replace(/\.docx$/i, '')
  if (RESERVED.test(cleaned)) cleaned = `_${cleaned}`
  if (cleaned.length > 120) cleaned = cleaned.slice(0, 120).trim()
  return `${cleaned}.docx`
}

export function safeZipFilename(name: string, fallback = 'lesson_plans.zip'): string {
  const base = (name || fallback).replace(/\.zip$/i, '')
  let cleaned = base.replace(ILLEGAL, '_').replace(/\s+/g, ' ').trim()
  if (!cleaned) cleaned = fallback.replace(/\.zip$/i, '')
  if (RESERVED.test(cleaned)) cleaned = `_${cleaned}`
  if (cleaned.length > 120) cleaned = cleaned.slice(0, 120).trim()
  return `${cleaned}.zip`
}

/**
 * Make ZIP member names unique without dropping a plan.
 *
 * Two lessons can legitimately share subject/class/week/date (e.g. two periods
 * on the same day). The server pattern alone would collide; a suffix keeps
 * every plan in the archive and preserves input order.
 */
export function uniqueNames(names: string[]): string[] {
  const used = new Set<string>()
  return names.map((name, index) => {
    const safe = safeDocxFilename(name || `lesson_${index + 1}.docx`)
    let candidate = safe
    let counter = 2
    while (used.has(candidate.toLowerCase())) {
      candidate = safe.replace(/\.docx$/i, `_${counter}.docx`)
      counter += 1
    }
    used.add(candidate.toLowerCase())
    return candidate
  })
}

/** Trigger a download and release the object URL only after the browser owns it. */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.rel = 'noopener'
  anchor.style.display = 'none'
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  // Chrome aborts a download when the URL is revoked in the same task as the
  // click. Release it on the next tick; the browser has taken ownership.
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
