'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ArrowLeft, CheckCircle, AlertCircle, Save, Loader2 } from 'lucide-react'
import { api } from '@/lib/api'
import { resolveRouteId } from '@/lib/route-params'
import { Header } from '@/components/header'

interface LessonData {
  id: string
  job_id: string
  scheme_id: string
  week_number: number
  lesson_number: number
  lesson_date: string | null
  class_level: string
  subject: string
  strand: string | null
  sub_strand: string | null
  content_standard: string | null
  indicators: string[] | null
  lesson_topic: string | null
  introduction: string | null
  assessment: string | null
  conclusion: string | null
  status: string
  teacher_edited: boolean
}

export default function LessonDetailPage() {
  const params = useParams()
  const lessonId = resolveRouteId(params.id, 'lessons')

  const [lesson, setLesson] = useState<LessonData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Editable fields
  const [topic, setTopic] = useState('')
  const [introduction, setIntroduction] = useState('')
  const [assessment, setAssessment] = useState('')
  const [conclusion, setConclusion] = useState('')
  // Optional AI section regeneration (existing /api/ai/regenerate-section)
  const [regenBusy, setRegenBusy] = useState<string | null>(null)
  const [regenNote, setRegenNote] = useState<string | null>(null)
  //: What AI would actually do for this teacher's selected mode.
  const [aiStatus, setAiStatus] = useState<{
    active: boolean; provider: string | null; mode: string; reason: string | null;
  } | null>(null)

  useEffect(() => {
    load()
    let mode = 'BASIC'
    try {
      const saved = window.localStorage.getItem('schemeknit.ai_mode')
      if (saved && saved !== 'OFF') mode = saved
    } catch { /* storage unavailable */ }
    api.getAiStatus(mode).then(setAiStatus).catch(() => setAiStatus(null))
  }, [lessonId])

  const load = async () => {
    try {
      setLoading(true)
      const data = await api.getLesson(lessonId)
      setLesson(data)
      setTopic(data.lesson_topic || '')
      setIntroduction(data.introduction || '')
      setAssessment(data.assessment || '')
      setConclusion(data.conclusion || '')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load lesson')
    } finally {
      setLoading(false)
    }
  }

  const handleRegenerate = async (section: 'introduction' | 'assessment' | 'conclusion') => {
    if (!lesson) return
    try {
      setRegenBusy(section)
      setRegenNote(null)
      setError(null)
      // Stable idempotency key for this user action so a retried submission
      // cannot consume a second lifetime AI generation.
      const requestId = `${lesson.id}:${section}:${Date.now()}`
      // Use the teacher's last chosen AI mode. This is NOT hard-coded to a
      // single provider: OFF (or unset) resolves to BASIC, which lets the
      // backend auto-select whichever real provider is configured, and report
      // an accurate diagnostic when none is.
      let mode = 'BASIC'
      try {
        const saved = window.localStorage.getItem('schemeknit.ai_mode')
        if (saved && saved !== 'OFF') mode = saved
      } catch { /* storage unavailable */ }
      const res = await api.regenerateSection(lesson.id, section, mode, '', requestId)
      const text = res.new_content || ''
      if (section === 'introduction') setIntroduction(text)
      if (section === 'assessment') setAssessment(text)
      if (section === 'conclusion') setConclusion(text)
      setRegenNote(
        `AI suggestion inserted by ${res.provider || 'provider'} (mode: ${res.mode || mode}). ` +
        'Review and Save to keep it.'
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'AI regeneration unavailable')
    } finally {
      setRegenBusy(null)
    }
  }

  const handleSave = async () => {
    try {
      setSaving(true)
      setSaved(false)
      const updated = await api.updateLesson(lessonId, {
        lesson_topic: topic,
        introduction,
        assessment,
        conclusion,
      })
      setLesson(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save lesson')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">Loading lesson...</p>
        </div>
      </div>
    )
  }

  if (error && !lesson) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Card className="max-w-md">
          <CardContent className="p-8 text-center">
            <AlertCircle className="h-12 w-12 text-destructive mx-auto mb-4" />
            <p className="text-destructive mb-4">{error}</p>
            <Button onClick={load}>Try Again</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  if (!lesson) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Card className="max-w-md">
          <CardContent className="p-8 text-center">
            <p className="text-muted-foreground mb-4">Lesson not found</p>
            <Link href="/lessons"><Button>Back to Lesson Plans</Button></Link>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-4 py-8 max-w-4xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">
              Week {lesson.week_number} &bull; Lesson {lesson.lesson_number}
            </h1>
            <p className="text-muted-foreground">
              {lesson.subject} &bull; {lesson.class_level}
              {lesson.lesson_date ? ` &bull; ${lesson.lesson_date}` : ''}
              {lesson.teacher_edited ? ' &bull; Edited' : ''}
            </p>
          </div>
          <Link href="/lessons">
            <Button variant="outline">
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back to Lesson Plans
            </Button>
          </Link>
        </div>

        {/* Curriculum context (read-only) */}
        <Card className="mb-6">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Curriculum Context</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {lesson.strand && (
              <p><span className="text-muted-foreground">Strand:</span> {lesson.strand}</p>
            )}
            {lesson.sub_strand && (
              <p><span className="text-muted-foreground">Sub-strand:</span> {lesson.sub_strand}</p>
            )}
            {lesson.content_standard && (
              <p><span className="text-muted-foreground">Content Standard:</span> {lesson.content_standard}</p>
            )}
            {lesson.indicators && lesson.indicators.length > 0 && (
              <div>
                <p className="text-muted-foreground mb-1">Indicators:</p>
                <ul className="list-disc list-inside space-y-0.5">
                  {lesson.indicators.map((ind, i) => <li key={i}>{ind}</li>)}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Editable fields */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Lesson Plan</CardTitle>
            <CardDescription>Edit the fields below and save your changes</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-2 pb-1">
              <span className="text-sm text-muted-foreground">Optional AI assist:</span>
              {(['introduction', 'assessment', 'conclusion'] as const).map((s) => (
                <Button
                  key={s}
                  size="sm"
                  variant="outline"
                  disabled={regenBusy !== null}
                  onClick={() => handleRegenerate(s)}
                >
                  {regenBusy === s ? 'Generating...' : `Suggest ${s}`}
                </Button>
              ))}
            </div>
            <span className="text-xs text-muted-foreground">
              {aiStatus
                ? aiStatus.active
                  ? `AI active · provider: ${aiStatus.provider}`
                  : 'No AI provider available — suggestions are disabled until one is configured.'
                : ''}
            </span>
            {regenNote && <p className="text-sm text-green-600">{regenNote}</p>}
            <div>
              <label className="block text-sm font-medium mb-2">Lesson Topic</label>
              <input
                type="text"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                className="w-full px-3 py-2 border rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Introduction / Starter</label>
              <textarea
                value={introduction}
                onChange={(e) => setIntroduction(e.target.value)}
                rows={4}
                className="w-full px-3 py-2 border rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Assessment</label>
              <textarea
                value={assessment}
                onChange={(e) => setAssessment(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 border rounded-md"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Conclusion / Reflection</label>
              <textarea
                value={conclusion}
                onChange={(e) => setConclusion(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 border rounded-md"
              />
            </div>

            <div className="flex items-center gap-3">
              <Button onClick={handleSave} disabled={saving}>
                {saving ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4 mr-2" />
                    Save Changes
                  </>
                )}
              </Button>
              {saved && (
                <span className="text-sm text-green-600 flex items-center">
                  <CheckCircle className="h-4 w-4 mr-1" />
                  Saved
                </span>
              )}
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </CardContent>
        </Card>
      </main>
    </div>
  )
}
