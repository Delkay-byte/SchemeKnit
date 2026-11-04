/** Pure parsing for teacher multiline list fields (references / TLRs).
 *
 *  Typing is never normalized per keystroke. A value is parsed only when the
 *  field is saved or generation payloads are built: one entry per line,
 *  leading/trailing whitespace trimmed per entry, blank lines ignored, and
 *  spaces inside an entry preserved exactly.
 */
export function parseMultilineEntries(text: string): string[] {
  return String(text || '')
    .split(/\r?\n/)
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0)
}

/** Serialize entries for display in the textarea (one per line). */
export function formatMultilineEntries(entries: string[] | null | undefined): string {
  return (entries || []).join('\n')
}
