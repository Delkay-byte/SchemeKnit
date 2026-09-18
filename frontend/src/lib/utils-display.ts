// SchemeKnit display utilities

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function formatCurrency(amount: number): string {
  return `GH\u20B5 ${amount.toFixed(2)}`
}

/**
 * Format a server timestamp for display.
 * The API emits UTC ISO strings with no timezone suffix; without the explicit
 * `Z` those would be read as local time and show the wrong hour.
 */
export function formatActivationDate(value: string | null | undefined): string {
  if (!value) return '\u2014'
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(value)
  const parsed = new Date(hasZone ? value : `${value}Z`)
  if (Number.isNaN(parsed.getTime())) return '\u2014'
  return parsed.toLocaleString()
}

export function formatStatus(status: string): string {
  const map: Record<string, string> = {
    uploaded: 'Uploaded',
    extracted: 'Extracted',
    needs_review: 'Needs Review',
    approved: 'Approved',
    ready_to_generate: 'Ready to Generate',
    generating: 'Generating',
    generated: 'Generated',
    edited: 'Edited',
    completed: 'Completed',
    pending: 'Pending',
    verified: 'Verified',
    rejected: 'Rejected',
    cancelled: 'Cancelled',
    active: 'Active',
    inactive: 'Inactive',
  }
  return map[status] || status.charAt(0).toUpperCase() + status.slice(1)
}

export function getStatusColor(status: string): string {
  const map: Record<string, string> = {
    uploaded: 'bg-blue-100 text-blue-800',
    extracted: 'bg-yellow-100 text-yellow-800',
    needs_review: 'bg-orange-100 text-orange-800',
    approved: 'bg-green-100 text-green-800',
    generating: 'bg-purple-100 text-purple-800',
    generated: 'bg-green-100 text-green-800',
    completed: 'bg-green-100 text-green-800',
    pending: 'bg-yellow-100 text-yellow-800',
    verified: 'bg-green-100 text-green-800',
    rejected: 'bg-red-100 text-red-800',
  }
  return map[status] || 'bg-gray-100 text-gray-800'
}

export function formatEducationalLevel(level: string): string {
  const map: Record<string, string> = {
    early_childhood: 'Early Childhood',
    primary: 'Primary',
    jhs: 'Junior High School',
    shs: 'Senior High School',
  }
  return map[level.toLowerCase().replace(/ /g, '_')] || level
}

export function formatTemplateFamily(family: string): string {
  const map: Record<string, string> = {
    early_childhood: 'Early Childhood',
    primary: 'Primary',
    jhs: 'Junior High School',
    shs: 'Senior High School',
  }
  return map[family] || family
}

export function getSchemeNextAction(status: string): { label: string; href: string } | null {
  switch (status) {
    case 'uploaded':
    case 'extracted':
      return { label: 'Review Curriculum', href: '' }
    case 'approved':
      return { label: 'Configure & Generate', href: '' }
    default:
      return null
  }
}

export function getSchemeWorkflowStep(status: string): number {
  const steps = ['uploaded', 'extracted', 'approved', 'generating', 'generated', 'completed']
  const idx = steps.indexOf(status)
  return idx >= 0 ? idx + 1 : 0
}
