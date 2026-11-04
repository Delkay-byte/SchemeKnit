'use client'

/**
 * Multiline list editor for teacher-entered values (references, TLRs).
 *
 * The visible textarea keeps the teacher's EXACT typing while they type:
 * spaces and newlines are never trimmed on every keystroke. Parsing happens
 * only when the value is read for saving/generation — blank lines are
 * dropped, leading/trailing whitespace is removed per entry, and separate
 * lines are never merged.
 */

import { useEffect, useRef, useState } from 'react'
import { TextArea } from '@/components/ui/field'
import { formatMultilineEntries, parseMultilineEntries } from '@/lib/multiline'

export interface MultilineListFieldProps {
  id: string
  value: string[]
  onChange: (entries: string[]) => void
  placeholder?: string
  rows?: number
  ariaLabel?: string
  disabled?: boolean
}

export function MultilineListField({
  id,
  value,
  onChange,
  placeholder,
  rows = 3,
  ariaLabel,
  disabled,
}: MultilineListFieldProps) {
  const [text, setText] = useState(() => formatMultilineEntries(value))
  const focused = useRef(false)

  // External changes (config reload, undo in the parent) update the editor,
  // but never while the teacher is typing: the raw text is authoritative then.
  useEffect(() => {
    if (!focused.current) {
      setText(formatMultilineEntries(value))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(value || [])])

  return (
    <TextArea
      id={id}
      aria-label={ariaLabel}
      rows={rows}
      value={text}
      disabled={disabled}
      placeholder={placeholder}
      spellCheck
      onFocus={() => {
        focused.current = true
      }}
      onBlur={() => {
        focused.current = false
        // Normalize only on deliberate completion, never per keystroke.
        const entries = parseMultilineEntries(text)
        setText(formatMultilineEntries(entries))
        onChange(entries)
      }}
      onChange={(event) => {
        const next = event.target.value
        // Keep the raw text (including the space the teacher just typed).
        setText(next)
        // Publish parsed entries immediately so a Generate click without a
        // blur still carries the latest configuration.
        onChange(parseMultilineEntries(next))
      }}
    />
  )
}
