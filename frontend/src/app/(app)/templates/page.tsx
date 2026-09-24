'use client'

import { useState, useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Banner } from '@/components/ui/banner'
import { Badge, StatusPill, type StatusTone } from '@/components/ui/badge'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  ConfirmDialog,
} from '@/components/ui/dialog'
import { FileText, CheckCircle, Upload, Eye, Archive, Pencil, RefreshCw } from 'lucide-react'
import { api } from '@/lib/api'
import { PageHeader } from '@/components/ui/page-header'
import { Template } from '@/types'
import { formatEducationalLevel, formatTemplateFamily } from '@/lib/utils-display'

const TEACHFLOW_FIELD_OPTIONS: { value: string; label: string }[] = [
  { value: 'school_name', label: 'School Name' },
  { value: 'teacher_name', label: 'Teacher' },
  { value: 'lesson_date', label: 'Lesson Date' },
  { value: 'class_level', label: 'Class' },
  { value: 'subject', label: 'Subject' },
  { value: 'class_size', label: 'Class Size' },
  { value: 'duration_minutes', label: 'Duration (minutes)' },
  { value: 'week_number', label: 'Week Number' },
  { value: 'lesson_number', label: 'Lesson Number' },
  { value: 'term', label: 'Term' },
  { value: 'academic_year', label: 'Academic Year' },
  { value: 'strand', label: 'Strand' },
  { value: 'sub_strand', label: 'Sub-strand' },
  { value: 'content_standard', label: 'Content Standard' },
  { value: 'content_standard_code', label: 'Content Standard Code' },
  { value: 'indicators', label: 'Indicators' },
  { value: 'indicator_codes', label: 'Indicator Codes' },
  { value: 'learning_objectives', label: 'Learning Objectives' },
  { value: 'core_competencies', label: 'Core Competencies' },
  { value: 'teaching_learning_resources', label: 'Teaching/Learning Resources' },
  { value: 'previous_knowledge', label: 'Previous Knowledge' },
  { value: 'introduction', label: 'Introduction' },
  { value: 'main_activities', label: 'Main Activities' },
  { value: 'learner_activities', label: 'Learner Activities' },
  { value: 'teacher_activities', label: 'Teacher Activities' },
  { value: 'assessment', label: 'Assessment' },
  { value: 'conclusion', label: 'Conclusion / Reflection' },
  { value: 'references', label: 'References' },
  { value: 'lesson_topic', label: 'Lesson Topic' },
  { value: 'homework', label: 'Homework' },
]

const LEVELS = ['Early Childhood', 'Primary', 'Junior High School', 'Senior High School']
const FAMILIES = ['early_childhood', 'primary', 'jhs', 'shs']

type WizardStep = 'upload' | 'mapping' | 'preview'

interface MappingRow {
  label: string
  field: string | null
  confidence: string
  match_kind: string
  custom: boolean
  teacher_confirmed: boolean
}

export default function TemplatesPage() {
  const [templates, setTemplates] = useState<Template[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  // Wizard state
  const [wizardOpen, setWizardOpen] = useState(false)
  const [wizardStep, setWizardStep] = useState<WizardStep>('upload')
  const [sampleFile, setSampleFile] = useState<File | null>(null)
  const [tplName, setTplName] = useState('')
  const [tplLevel, setTplLevel] = useState('Junior High School')
  const [tplFamily, setTplFamily] = useState('jhs')
  const [tplDesc, setTplDesc] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [analysis, setAnalysis] = useState<any>(null)
  const [mappings, setMappings] = useState<MappingRow[]>([])
  const [saving, setSaving] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  // Preview state
  const [previewTpl, setPreviewTpl] = useState<any>(null)
  const [previewData, setPreviewData] = useState<any>(null)
  const [pendingArchive, setPendingArchive] = useState<{ id: string; name: string } | null>(null)
  // Version dialog — replaces the raw browser prompt with a real dialog.
  const [versionDialog, setVersionDialog] = useState<{ id: string; current: string; value: string } | null>(null)

  useEffect(() => {
    loadTemplates()
  }, [])

  const loadTemplates = async () => {
    try {
      setLoading(true)
      const response = await api.listTemplates()
      setTemplates(response.templates || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load templates')
    } finally {
      setLoading(false)
    }
  }

  const builtin = templates.filter((t: any) => !t.is_custom)
  const mine = templates.filter((t: any) => t.is_custom)

  // Teacher-facing production selection shows ONLY the approved groups
  // (PART 10/29). The backend already filters out pending/draft/experimental
  // forms for teachers; group what remains by its approved_group so the
  // headings name the verified level, never a verification state or an
  // internal template id.
  const approvedGroups: Record<string, typeof builtin> = {}
  for (const t of builtin) {
    const key = (t as any).approved_group || 'Approved Templates'
    ;(approvedGroups[key] = approvedGroups[key] || []).push(t)
  }

  const startWizard = () => {
    setWizardOpen(true)
    setWizardStep('upload')
    setSampleFile(null)
    setAnalysis(null)
    setMappings([])
    setError(null)
  }

  const handleAnalyze = async () => {
    if (!sampleFile) {
      setError('Please choose a sample DOCX file first')
      return
    }
    try {
      setAnalyzing(true)
      setError(null)
      const res = await api.analyzeTemplateSample(sampleFile)
      setAnalysis(res)
      setMappings((res.structure?.mappings || []).map((m: any) => ({
        label: m.label,
        field: m.field,
        confidence: m.confidence,
        match_kind: m.match_kind,
        custom: m.custom,
        teacher_confirmed: false,
      })))
      if (!tplName) {
        setTplName((res.original_filename || 'My Template').replace(/\.docx$/i, ''))
      }
      setWizardStep('mapping')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sample analysis failed')
    } finally {
      setAnalyzing(false)
    }
  }

  const setMappingField = (label: string, value: string) => {
    setMappings((prev) => prev.map((m) =>
      m.label === label
        ? {
            ...m,
            field: value === '__custom__' ? null : value,
            custom: value === '__custom__',
            confidence: 'confirmed',
            teacher_confirmed: true,
          }
        : m
    ))
  }

  const handleSave = async () => {
    if (!tplName.trim()) {
      setError('Template name is required')
      return
    }
    try {
      setSaving(true)
      setError(null)
      await api.saveCustomTemplate({
        analysis_id: analysis.analysis_id,
        name: tplName.trim(),
        educational_level: tplLevel,
        family: tplFamily,
        description: tplDesc,
        mappings: mappings.map((m) => ({
          label: m.label,
          field: m.field,
          custom: m.custom,
          teacher_confirmed: m.teacher_confirmed,
        })),
      })
      setWizardOpen(false)
      loadTemplates()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save template')
    } finally {
      setSaving(false)
    }
  }

  const openPreview = async (id: string) => {
    try {
      setError(null)
      const [detail, preview] = await Promise.all([
        api.getCustomTemplate(id),
        api.previewCustomTemplate(id),
      ])
      setPreviewTpl(detail)
      setPreviewData(preview)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load preview')
    }
  }

  const handleArchive = async (id: string) => {
    try {
      await api.archiveCustomTemplate(id)
      loadTemplates()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to archive template')
    }
  }

  const handleVersion = async () => {
    if (!versionDialog) return
    const v = versionDialog.value.trim()
    if (!v) return
    try {
      await api.versionCustomTemplate(versionDialog.id, v)
      setVersionDialog(null)
      loadTemplates()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update version')
    }
  }

  const confidenceTone = (c: string): StatusTone => {
    const map: Record<string, StatusTone> = {
      high: 'success',
      medium: 'warning',
      manual: 'danger',
      confirmed: 'info',
    }
    return map[c] || 'neutral'
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">Loading templates...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <main className="container mx-auto px-4 py-8">
        <div className="mx-auto max-w-5xl">
          <PageHeader
            className="mb-6"
            title="Lesson Plan Templates"
            description="Built-in SchemeKnit formats plus your own templates created from sample lesson plans."
            actions={
              <Button onClick={startWizard}>
                <Upload className="mr-1.5 h-4 w-4" />
                Create Template from Sample
              </Button>
            }
          />

          {error && !wizardOpen && (
            <Banner tone="danger" className="mb-6">{error}</Banner>
          )}

          {/* MY TEMPLATES — a document library table, not a card wall. */}
          <section aria-labelledby="my-templates-heading" className="mb-8">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <h2 id="my-templates-heading" className="text-lg font-semibold text-[#102A43]">
                My Templates <span className="text-muted-foreground">({mine.length})</span>
              </h2>
            </div>
            {mine.length === 0 ? (
              <SurfaceCard data-empty className="px-6 py-10 text-center">
                <FileText className="mx-auto mb-4 h-12 w-12 text-slate-300" aria-hidden="true" />
                <p className="font-medium text-[#102A43]">No custom templates yet</p>
                <p className="mb-4 mt-1 text-sm text-muted-foreground">
                  Upload a sample lesson plan and SchemeKnit will learn its structure.
                </p>
                <Button variant="outline" onClick={startWizard}>Create Template from Sample</Button>
              </SurfaceCard>
            ) : (
              <SurfaceCard data-my-templates className="overflow-hidden">
                <Table className="min-w-[760px]">
                  <TableHeader>
                    <TableRow className="bg-muted/50 hover:bg-muted/50">
                      <TableHead>Template</TableHead>
                      <TableHead>Family</TableHead>
                      <TableHead>Level</TableHead>
                      <TableHead>Version</TableHead>
                      <TableHead>Sections</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {mine.map((t: any) => (
                      <TableRow key={t.id}>
                        <TableCell className="max-w-[260px]">
                          <span className="block font-medium">{t.name}</span>
                          <span className="block truncate text-xs text-muted-foreground">
                            {t.description || 'Custom template from sample lesson plan.'}
                          </span>
                        </TableCell>
                        <TableCell className="whitespace-nowrap">{formatTemplateFamily(t.family)}</TableCell>
                        <TableCell className="whitespace-nowrap">{formatEducationalLevel(t.educational_level)}</TableCell>
                        <TableCell>
                          <StatusPill tone="accent">v{t.version || '1.0'}</StatusPill>
                        </TableCell>
                        <TableCell>
                          {(t.section_count ?? 0) > 0 ? (
                            <Badge variant="neutral">{t.section_count} sections</Badge>
                          ) : (
                            <span className="text-xs text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex flex-wrap justify-end gap-1">
                            <Button size="sm" variant="ghost" onClick={() => openPreview(t.id)}>
                              <Eye className="mr-1 h-4 w-4" /> Preview
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => setVersionDialog({ id: t.id, current: t.version || '1.0', value: t.version || '1.0' })}
                            >
                              <RefreshCw className="mr-1 h-4 w-4" /> Version
                            </Button>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="text-muted-foreground hover:text-destructive"
                              onClick={() => setPendingArchive({ id: t.id, name: t.name })}
                            >
                              <Archive className="mr-1 h-4 w-4" /> Archive
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </SurfaceCard>
            )}
          </section>

          {/* APPROVED TEMPLATES — restrained grouped rows, family by family. */}
          <section aria-labelledby="approved-templates-heading">
            <h2 id="approved-templates-heading" className="mb-4 text-lg font-semibold text-[#102A43]">
              Approved Templates <span className="text-muted-foreground">({builtin.length})</span>
            </h2>
            {Object.entries(approvedGroups).map(([groupName, items]) => (
              <div key={groupName} className="mb-6">
                <div className="mb-2 flex items-center gap-2">
                  <CheckCircle className="h-4 w-4 text-green-600" aria-hidden="true" />
                  <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                    {groupName}
                  </h3>
                </div>
                <SurfaceCard data-approved-group className="overflow-hidden">
                  {items.map((template) => {
                    const isSelected = selectedId === template.id
                    const isDefault = template.is_default
                    return (
                      <div
                        key={template.id}
                        onClick={() => setSelectedId(template.id)}
                        className={`flex cursor-pointer flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3 transition-colors last:border-b-0 hover:bg-slate-50 ${
                          isSelected ? 'bg-[#04A9CE]/5' : ''
                        }`}
                      >
                        <div className="flex min-w-0 items-center gap-3">
                          <span className="rounded-lg bg-[#102A43]/8 p-2 text-[#04769B]">
                            <FileText className="h-5 w-5" aria-hidden="true" />
                          </span>
                          <div className="min-w-0">
                            <p className="truncate font-semibold text-[#102A43]">{template.name}</p>
                            <p className="truncate text-xs text-muted-foreground">
                              {formatTemplateFamily(template.family)} &bull; {formatEducationalLevel(template.educational_level)}
                            </p>
                          </div>
                        </div>
                        <div className="flex shrink-0 flex-wrap items-center gap-2">
                          {isDefault && (
                            <Badge variant="info">
                              <CheckCircle className="mr-1 h-3 w-3" aria-hidden="true" />
                              Default
                            </Badge>
                          )}
                          {isSelected && (
                            <StatusPill tone="success">Selected</StatusPill>
                          )}
                          <Button
                            size="sm"
                            variant={isSelected ? 'default' : 'outline'}
                            aria-pressed={isSelected}
                          >
                            {isSelected ? 'Selected' : 'Use This Template'}
                          </Button>
                        </div>
                      </div>
                    )
                  })}
                </SurfaceCard>
              </div>
            ))}
          </section>

          {/* About */}
          <SurfaceCard className="mt-8 px-5 py-5 sm:px-6">
            <h2 className="text-sm font-semibold text-[#102A43]">About Templates</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Built-in templates are SchemeKnit Standard formats organized by educational level.
              Your custom templates reproduce the structure of sample lesson plans you upload,
              and can be selected during lesson generation. Only formats verified against official
              sources are labelled official; everything else is a SchemeKnit Standard or custom format.
            </p>
          </SurfaceCard>
        </div>

        {/* CREATE-FROM-SAMPLE WIZARD */}
        {wizardOpen && (
          <Dialog open onOpenChange={setWizardOpen}>
            <DialogContent className="max-w-3xl">
              <DialogHeader>
                <DialogTitle>Create Template from Sample</DialogTitle>
                <DialogDescription>
                  {wizardStep === 'upload' && 'Step 1 of 3 — Upload a sample lesson plan (DOCX)'}
                  {wizardStep === 'mapping' && 'Step 2 of 3 — Review detected fields and mappings'}
                  {wizardStep === 'preview' && 'Step 3 of 3 — Preview and save'}
                </DialogDescription>
              </DialogHeader>
              {error && <Banner tone="danger">{error}</Banner>}
              <div className="space-y-4">
                {wizardStep === 'upload' && (
                  <>
                    <div
                      role="button"
                      tabIndex={0}
                      aria-label={sampleFile ? `Selected sample: ${sampleFile.name}` : 'Choose a sample DOCX file (max 10 MB)'}
                      className="cursor-pointer rounded-lg border-2 border-dashed p-8 text-center hover:border-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#04A9CE]"
                      onClick={() => fileRef.current?.click()}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          fileRef.current?.click()
                        }
                      }}
                    >
                      {sampleFile ? (
                        <p className="font-semibold">{sampleFile.name}</p>
                      ) : (
                        <p className="text-muted-foreground">Click to choose a sample DOCX file (max 10 MB)</p>
                      )}
                      <input
                        ref={fileRef}
                        type="file"
                        accept=".docx"
                        className="hidden"
                        onChange={(e) => setSampleFile(e.target.files?.[0] || null)}
                      />
                    </div>
                    <Input
                      type="text"
                      placeholder="Template name (e.g. My JHS Science Format)"
                      value={tplName}
                      onChange={(e) => setTplName(e.target.value)}
                    />
                    <div className="grid gap-4 md:grid-cols-2">
                      <Select value={tplLevel} onChange={(e) => setTplLevel(e.target.value)} aria-label="Educational level">
                        {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
                      </Select>
                      <Select value={tplFamily} onChange={(e) => setTplFamily(e.target.value)} aria-label="Template family">
                        {FAMILIES.map((f) => <option key={f} value={f}>{f}</option>)}
                      </Select>
                    </div>
                    <Input
                      type="text"
                      placeholder="Description (optional)"
                      value={tplDesc}
                      onChange={(e) => setTplDesc(e.target.value)}
                    />
                    <div className="flex gap-2">
                      <Button onClick={handleAnalyze} disabled={analyzing || !sampleFile}>
                        {analyzing ? 'Analyzing...' : 'Analyze Sample'}
                      </Button>
                      <Button variant="outline" onClick={() => setWizardOpen(false)}>Cancel</Button>
                    </div>
                  </>
                )}

                {wizardStep === 'mapping' && analysis && (
                  <>
                    <p className="text-sm text-muted-foreground">
                      Detected {analysis.mapping_count} field labels in {analysis.structure?.meta?.table_count ?? 0} tables
                      from <span className="font-medium">{analysis.original_filename}</span>.
                      Correct any mapping before saving.
                    </p>
                    <div className="overflow-x-auto rounded-lg border">
                      <table className="w-full min-w-[520px] text-sm">
                        <thead>
                          <tr className="border-b bg-muted/50">
                            <th className="p-2 text-left">Detected field</th>
                            <th className="p-2 text-left">SchemeKnit field</th>
                            <th className="p-2 text-left">Confidence</th>
                          </tr>
                        </thead>
                        <tbody>
                          {mappings.map((m) => (
                            <tr key={m.label} className="border-b">
                              <td className="p-2 font-medium">{m.label}</td>
                              <td className="p-2">
                                <Select
                                  value={m.custom ? '__custom__' : (m.field || '__custom__')}
                                  onChange={(e) => setMappingField(m.label, e.target.value)}
                                  className="h-9 rounded-md px-2 text-sm"
                                >
                                  <option value="__custom__">Keep as custom field</option>
                                  {TEACHFLOW_FIELD_OPTIONS.map((o) => (
                                    <option key={o.value} value={o.value}>{o.label}</option>
                                  ))}
                                </Select>
                              </td>
                              <td className="p-2">
                                <StatusPill tone={confidenceTone(m.confidence)}>
                                  {m.confidence}
                                </StatusPill>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {mappings.length === 0 && (
                      <Banner tone="warning">
                        SchemeKnit could not confidently map this template. No field labels were detected —
                        try a different sample, or cancel.
                      </Banner>
                    )}
                    <div className="flex gap-2">
                      <Button variant="outline" onClick={() => setWizardStep('upload')}>Back</Button>
                      <Button onClick={() => setWizardStep('preview')}>Preview</Button>
                    </div>
                  </>
                )}

                {wizardStep === 'preview' && analysis && (
                  <>
                    <p className="text-sm text-muted-foreground">
                      Preview of <span className="font-medium">{tplName || 'your template'}</span> — labels from your
                      sample, values filled at generation time.
                    </p>
                    {(analysis.structure?.tables || []).slice(0, 3).map((t: any) => (
                      <div key={t.index} className="rounded-lg border p-3">
                        <p className="mb-2 text-xs font-medium">
                          Table {t.index + 1} — {t.rows} rows × {t.cols} columns
                        </p>
                        <div className="space-y-1">
                          {(t.cells || []).slice(0, 12).map((c: any, i: number) => (
                            <div key={i} className="flex gap-2 border-b py-1 text-xs">
                              <span className="min-w-[140px] font-semibold">{c.label || '(content)'}</span>
                              <span className="flex-1 truncate text-muted-foreground">
                                {c.field ? `→ ${c.field}` : c.custom ? '(kept as custom field)' : '(structural)'}
                              </span>
                              <StatusPill
                                tone={confidenceTone(
                                  mappings.find((m) => m.label === c.label)?.confidence || c.confidence
                                )}
                                className="rounded px-1.5 py-0.5 text-[10px]"
                              >
                                {mappings.find((m) => m.label === c.label)?.confidence || c.confidence}
                              </StatusPill>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                    <div className="flex gap-2">
                      <Button variant="outline" onClick={() => setWizardStep('mapping')}>Edit Mapping</Button>
                      <Button onClick={handleSave} disabled={saving}>
                        {saving ? 'Saving...' : 'Save Template'}
                      </Button>
                    </div>
                  </>
                )}
              </div>
            </DialogContent>
          </Dialog>
        )}

        {/* SAVED TEMPLATE PREVIEW */}
        {previewTpl && (
          <Dialog open onOpenChange={(open) => { if (!open) { setPreviewTpl(null); setPreviewData(null) } }}>
            <DialogContent className="max-w-3xl">
              <DialogHeader>
                <DialogTitle>{previewTpl.name} <span className="text-sm font-normal">v{previewTpl.version}</span></DialogTitle>
                <DialogDescription>
                  {previewTpl.original_filename ? `From ${previewTpl.original_filename} • ` : ''}
                  {formatEducationalLevel(previewTpl.educational_level)} • {previewTpl.status}
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                {(previewData?.tables || []).slice(0, 4).map((t: any) => (
                  <div key={t.index} className="rounded-lg border p-3">
                    <p className="mb-2 text-xs font-medium">Table {t.index + 1} — {t.rows}×{t.cols}</p>
                    <div className="space-y-1">
                      {(t.cells || []).slice(0, 14).map((c: any, i: number) => (
                        <div key={i} className="flex gap-2 border-b py-1 text-xs">
                          <span className="min-w-[140px] font-semibold">{c.label || '(content)'}</span>
                          <span className="flex-1 truncate text-muted-foreground">
                            {c.sample_value ? `sample: ${c.sample_value.slice(0, 60)}` : c.field ? `→ ${c.field}` : '—'}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
                {(!previewData?.tables || previewData.tables.length === 0) && (
                  <p className="text-sm text-muted-foreground">No structural preview stored for this template.</p>
                )}
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setVersionDialog({ id: previewTpl.id, current: previewTpl.version || '1.0', value: previewTpl.version || '1.0' })}
                  >
                    <Pencil className="mr-1 h-4 w-4" /> New Version
                  </Button>
                  <Button variant="outline" onClick={() => { setPreviewTpl(null); setPreviewData(null) }}>Close</Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        )}

        {/* VERSION DIALOG — replaces prompt() */}
        <Dialog open={versionDialog !== null} onOpenChange={(open) => { if (!open) setVersionDialog(null) }}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>New version</DialogTitle>
              <DialogDescription>
                Current version {versionDialog?.current}. Use X.Y format, e.g. 1.1 or 2.0.
              </DialogDescription>
            </DialogHeader>
            <Input
              type="text"
              aria-label="New version"
              value={versionDialog?.value || ''}
              onChange={(e) => setVersionDialog(v => (v ? { ...v, value: e.target.value } : v))}
              autoFocus
            />
            <div className="flex gap-2">
              <Button onClick={handleVersion} disabled={!versionDialog?.value.trim()}>
                Update Version
              </Button>
              <Button variant="outline" onClick={() => setVersionDialog(null)}>
                Cancel
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        <ConfirmDialog
          open={pendingArchive !== null}
          onOpenChange={(open) => {
            if (!open) setPendingArchive(null)
          }}
          title="Archive template"
          message={`Archive template "${pendingArchive?.name}"? It will be hidden from generation but history is kept.`}
          confirmLabel="Archive"
          destructive
          onConfirm={() => {
            if (pendingArchive !== null) handleArchive(pendingArchive.id)
          }}
        />
      </main>
    </div>
  )
}
