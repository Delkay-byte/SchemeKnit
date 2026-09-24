'use client'

import { useState, useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Banner } from '@/components/ui/banner'
import { StatusPill, type StatusTone } from '@/components/ui/badge'
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

  const handleVersion = async (id: string, current: string) => {
    const v = prompt(`New version for this template (current ${current}). Use X.Y format, e.g. 1.1 or 2.0:`, current)
    if (!v) return
    try {
      await api.versionCustomTemplate(id, v.trim())
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
        <div className="max-w-5xl mx-auto">
          <div className="mb-6">
            <PageHeader
              title="Lesson Plan Templates"
              description="Built-in SchemeKnit formats plus your own templates created from sample lesson plans."
            />
          </div>

          {error && <Banner tone="danger" className="mb-6">{error}</Banner>}

          {/* MY TEMPLATES */}
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">My Templates ({mine.length})</h3>
            <Button onClick={startWizard}>
              <Upload className="h-4 w-4 mr-1.5" />
              Create Template from Sample
            </Button>
          </div>
          {mine.length === 0 ? (
            <Card className="mb-8">
              <CardContent className="p-8 text-center">
                <FileText className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                <p className="font-medium mb-1">No custom templates yet</p>
                <p className="text-sm text-muted-foreground mb-4">
                  Upload a sample lesson plan and SchemeKnit will learn its structure.
                </p>
                <Button variant="outline" onClick={startWizard}>Create Template from Sample</Button>
              </CardContent>
            </Card>
          ) : (
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
              {mine.map((t: any) => (
                <Card key={t.id}>
                  <CardHeader>
                    <CardTitle className="text-lg">{t.name}</CardTitle>
                    <CardDescription className="text-sm">
                      {formatTemplateFamily(t.family)} &bull; {formatEducationalLevel(t.educational_level)}
                    </CardDescription>
                    <div className="flex gap-2 mt-2 text-xs">
                      <StatusPill tone="accent" className="rounded-full">v{t.version || '1.0'}</StatusPill>
                      <StatusPill tone="neutral" className="rounded-full">{t.source_type || 'custom'}</StatusPill>
                      {(t.section_count ?? 0) > 0 && (
                        <StatusPill tone="neutral" className="rounded-full">{t.section_count} sections</StatusPill>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm text-muted-foreground mb-4">
                      {t.description || 'Custom template from sample lesson plan.'}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      <Button size="sm" variant="outline" onClick={() => openPreview(t.id)}>
                        <Eye className="h-4 w-4 mr-1" /> Preview
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => handleVersion(t.id, t.version || '1.0')}>
                        <RefreshCw className="h-4 w-4 mr-1" /> Version
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => setPendingArchive({ id: t.id, name: t.name })}>
                        <Archive className="h-4 w-4 mr-1" /> Archive
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {/* BUILT-IN TEMPLATES */}
          <h3 className="text-lg font-semibold mb-4">Approved Templates ({builtin.length})</h3>
          {Object.entries(approvedGroups).map(([groupName, items]) => (
            <div key={groupName} className="mb-8">
              <div className="flex items-center gap-2 mb-3">
                <CheckCircle className="h-4 w-4 text-green-600" />
                <h4 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  {groupName}
                </h4>
              </div>
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
                {items.map((template) => {
                  const isSelected = selectedId === template.id
                  const isDefault = template.is_default
                  return (
                    <Card
                      key={template.id}
                      className={`cursor-pointer transition-all hover:shadow-lg ${
                        isSelected ? 'border-primary ring-2 ring-primary/20' :
                        isDefault ? 'border-primary/50' : ''
                      }`}
                      onClick={() => setSelectedId(template.id)}
                    >
                      <CardHeader>
                        <div className="flex items-start justify-between">
                          <div className="flex items-center space-x-3">
                            <div className="p-2 bg-primary/10 rounded-lg">
                              <FileText className="h-6 w-6 text-primary" />
                            </div>
                            <div>
                              <CardTitle className="text-lg">{template.name}</CardTitle>
                              <CardDescription className="text-sm">
                                {formatTemplateFamily(template.family)} &bull; {formatEducationalLevel(template.educational_level)}
                              </CardDescription>
                            </div>
                          </div>
                        </div>
                        <div className="flex gap-2 mt-2">
                          {isDefault && (
                            <span className="inline-flex items-center text-xs font-medium text-primary bg-primary/10 px-2 py-0.5 rounded-full">
                              <CheckCircle className="h-3 w-3 mr-1" />
                              Default
                            </span>
                          )}
                          {isSelected && (
                            <StatusPill tone="success" className="rounded-full">
                              Selected
                            </StatusPill>
                          )}
                        </div>
                      </CardHeader>
                      <CardContent>
                        <p className="text-sm text-muted-foreground mb-4">
                          {template.description || 'A professionally designed template for lesson plan formatting.'}
                        </p>
                        <div className="mt-4">
                          <Button variant={isSelected ? 'default' : 'outline'} size="sm" className="w-full">
                            {isSelected ? 'Selected' : 'Use This Template'}
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  )
                })}
              </div>
            </div>
          ))}

          <Card className="mt-8">
            <CardContent className="p-6">
              <h3 className="font-semibold mb-2">About Templates</h3>
              <p className="text-sm text-muted-foreground">
                Built-in templates are SchemeKnit Standard formats organized by educational level.
                Your custom templates reproduce the structure of sample lesson plans you upload,
                and can be selected during lesson generation. Only formats verified against official
                sources are labelled official; everything else is a SchemeKnit Standard or custom format.
              </p>
            </CardContent>
          </Card>
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
              <div className="space-y-4">
                {wizardStep === 'upload' && (
                  <>
                    <div
                      className="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer hover:border-primary"
                      onClick={() => fileRef.current?.click()}
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
                    <div className="grid md:grid-cols-2 gap-4">
                      <Select value={tplLevel} onChange={(e) => setTplLevel(e.target.value)}>
                        {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
                      </Select>
                      <Select value={tplFamily} onChange={(e) => setTplFamily(e.target.value)}>
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
                    <div className="border rounded-lg overflow-hidden">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b bg-muted/50">
                            <th className="text-left p-2">Detected field</th>
                            <th className="text-left p-2">SchemeKnit field</th>
                            <th className="text-left p-2">Confidence</th>
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
                                <StatusPill tone={confidenceTone(m.confidence)} className="rounded-full">
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
                      <div key={t.index} className="border rounded-lg p-3">
                        <p className="text-xs font-medium mb-2">
                          Table {t.index + 1} — {t.rows} rows × {t.cols} columns
                        </p>
                        <div className="space-y-1">
                          {(t.cells || []).slice(0, 12).map((c: any, i: number) => (
                            <div key={i} className="flex gap-2 text-xs border-b py-1">
                              <span className="font-semibold min-w-[140px]">{c.label || '(content)'}</span>
                              <span className="text-muted-foreground flex-1 truncate">
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
                  <div key={t.index} className="border rounded-lg p-3">
                    <p className="text-xs font-medium mb-2">Table {t.index + 1} — {t.rows}×{t.cols}</p>
                    <div className="space-y-1">
                      {(t.cells || []).slice(0, 14).map((c: any, i: number) => (
                        <div key={i} className="flex gap-2 text-xs border-b py-1">
                          <span className="font-semibold min-w-[140px]">{c.label || '(content)'}</span>
                          <span className="text-muted-foreground flex-1 truncate">
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
                  <Button variant="outline" onClick={() => handleVersion(previewTpl.id, previewTpl.version)}>
                    <Pencil className="h-4 w-4 mr-1" /> New Version
                  </Button>
                  <Button variant="outline" onClick={() => { setPreviewTpl(null); setPreviewData(null) }}>Close</Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        )}

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
