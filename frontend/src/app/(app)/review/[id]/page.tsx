'use client'

import { useState, useEffect } from 'react'
import { useRouter, useParams } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { StatusPill, type StatusTone } from '@/components/ui/badge'
import { ArrowLeft, ArrowRight, CheckCircle, AlertCircle, Info } from 'lucide-react'
import { api } from '@/lib/api'
import { resolveRouteId } from '@/lib/route-params'

interface WeekData {
  id: string
  week_number: number
  start_date: string
  end_date: string
  week_type: string
  strand: string | null
  sub_strand: string | null
  content_standards: string[]
  indicators: string[]
  resources: string[]
}

interface SchemeData {
  id: string
  filename: string
  subject: string
  class_level: string
  term: string
  academic_year: string
  weeks_count: number
  status: string
  // Multi-subject detection (§4)
  detection_status?: string
  detected_subjects?: string[]
  needs_subject_confirmation?: boolean
}

const WEEK_TYPE_LABELS: Record<string, string> = {
  instruction: 'Instruction',
  revision: 'Revision',
  assessment: 'Assessment',
  sba: 'SBA',
  other: 'Other',
}

export default function ReviewPage() {
  const router = useRouter()
  const params = useParams()
  const schemeId = resolveRouteId(params.id, 'review')

  const [scheme, setScheme] = useState<SchemeData | null>(null)
  const [weeks, setWeeks] = useState<WeekData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedWeek, setSelectedWeek] = useState<number>(1)
  const [validation, setValidation] = useState<any>(null)
  const [approving, setApproving] = useState(false)
  const [confirmingSubject, setConfirmingSubject] = useState<string | null>(null)

  useEffect(() => {
    loadSchemeData()
  }, [schemeId])

  const loadSchemeData = async () => {
    try {
      setLoading(true)
      const schemeData = await api.getScheme(schemeId)
      setScheme(schemeData)
      const weeksData = await api.getSchemeWeeks(schemeId)
      setWeeks(weeksData.weeks || [])
      if (weeksData.weeks && weeksData.weeks.length > 0) {
        setSelectedWeek(weeksData.weeks[0].week_number)
      }
      try {
        setValidation(await api.validateScheme(schemeId))
      } catch {
        setValidation(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load scheme data')
    } finally {
      setLoading(false)
    }
  }

  const handleApprove = async () => {
    try {
      setApproving(true)
      await api.approveScheme(schemeId)
      router.push(`/generate/${schemeId}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to approve scheme')
    } finally {
      setApproving(false)
    }
  }

  const handleConfirmSubject = async (subject: string) => {
    setConfirmingSubject(subject)
    setError(null)
    try {
      await api.confirmSubjectSection(schemeId, subject)
      await loadSchemeData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not confirm that subject')
    } finally {
      setConfirmingSubject(null)
    }
  }

  const currentWeek = weeks.find(w => w.week_number === selectedWeek)
  const weekTypeTone = (type: string): StatusTone => {
    const tones: Record<string, StatusTone> = {
      instruction: 'info',
      revision: 'warning',
      assessment: 'danger',
      sba: 'accent',
      other: 'neutral',
    }
    return tones[type] || tones.other
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">Loading scheme data...</p>
        </div>
      </div>
    )
  }

  if (error && !scheme) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Card className="max-w-md">
          <CardContent className="p-8 text-center">
            <AlertCircle className="h-12 w-12 text-destructive mx-auto mb-4" />
            <p className="text-destructive mb-4">{error}</p>
            <Button onClick={loadSchemeData}>Try Again</Button>
          </CardContent>
        </Card>
      </div>
    )
  }



  if (!scheme) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Card className="max-w-md">
          <CardContent className="p-8 text-center">
            <p className="text-muted-foreground mb-4">Scheme not found</p>
            <Link href="/dashboard"><Button>Go to Dashboard</Button></Link>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <main className="container mx-auto px-4 py-8">
        {/* Subject-section confirmation (§4). A document with several subjects
            must be confirmed before generation; nothing is generated from an
            unconfirmed section. */}
        {scheme.needs_subject_confirmation && (
          <Card className="mb-6 border-amber-300 bg-amber-50">
            <CardContent className="p-4">
              <p className="font-semibold text-sm mb-1">Multiple subjects detected</p>
              <p className="text-sm text-muted-foreground mb-3">
                This document contains more than one subject. Choose the subject
                you are teaching — only that section will be used.
              </p>
              <div className="flex flex-wrap gap-2">
                {(scheme.detected_subjects || []).map((s) => (
                  <Button
                    key={s}
                    size="sm"
                    variant="outline"
                    className="whitespace-normal"
                    disabled={confirmingSubject !== null}
                    onClick={() => handleConfirmSubject(s)}
                  >
                    {confirmingSubject === s ? 'Confirming…' : s}
                  </Button>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Scheme Info Banner */}
        <Card className="mb-6">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold">{scheme.filename}</h2>
                <p className="text-sm text-muted-foreground">
                  {scheme.subject} &bull; {scheme.class_level} &bull; {scheme.term}
                </p>
              </div>
              <div className="text-right text-sm text-muted-foreground">
                <p>{weeks.length} weeks extracted</p>
                <p>{weeks.filter(w => w.week_type === 'instruction').length} instructional weeks</p>
              </div>
            </div>
            {validation && !validation.is_valid && (
              <div className="mt-3 p-3 bg-yellow-50 border border-yellow-200 rounded-lg flex items-start gap-2">
                <AlertCircle className="h-4 w-4 text-yellow-600 mt-0.5" />
                <div className="text-sm text-yellow-800">
                  {validation.issues?.map((iss: any, i: number) => (
                    <p key={i}>{iss.message}</p>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="grid lg:grid-cols-4 gap-6">
          {/* Sidebar - Week Navigation */}
          <div className="lg:col-span-1">
            <Card>
              <CardHeader>
                <CardTitle>Weeks ({weeks.length})</CardTitle>
                <CardDescription>Select a week to review</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-1 max-h-[60vh] overflow-y-auto">
                  {weeks.map((week) => (
                    <button
                      key={week.id}
                      onClick={() => setSelectedWeek(week.week_number)}
                      className={`w-full text-left px-3 py-2 rounded-lg transition-colors ${
                        selectedWeek === week.week_number
                          ? 'bg-primary text-primary-foreground'
                          : 'hover:bg-muted'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-sm">Week {week.week_number}</span>
                        <StatusPill tone={weekTypeTone(week.week_type)} className="rounded-full">
                          {WEEK_TYPE_LABELS[week.week_type] || week.week_type}
                        </StatusPill>
                      </div>
                      <div className="text-xs opacity-75">{week.end_date}</div>
                    </button>
                  ))}
                </div>
              </CardContent>
            </Card>

            <Card className="mt-4">
              <CardContent className="p-4">
                <div className="text-sm space-y-1">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Total weeks:</span>
                    <span className="font-medium">{weeks.length}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Instruction:</span>
                    <span className="font-medium">{weeks.filter(w => w.week_type === 'instruction').length}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Special:</span>
                    <span className="font-medium">{weeks.filter(w => w.week_type !== 'instruction').length}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Main Content - Week Details */}
          <div className="lg:col-span-3">
            {weeks.length === 0 ? (
              <Card>
                <CardContent className="p-8 text-center">
                  <Info className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                  <p className="text-muted-foreground mb-4">No weeks found in the scheme</p>
                  <Link href="/dashboard"><Button>Go to Dashboard</Button></Link>
                </CardContent>
              </Card>
            ) : currentWeek ? (
              <>
                <Card className="mb-6">
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <div>
                        <CardTitle className="flex items-center gap-2">
                          Week {currentWeek.week_number}
                          <StatusPill tone={weekTypeTone(currentWeek.week_type)} className="rounded-full text-sm">
                            {WEEK_TYPE_LABELS[currentWeek.week_type] || currentWeek.week_type}
                          </StatusPill>
                        </CardTitle>
                        <CardDescription>
                          Week ending: {currentWeek.end_date}
                        </CardDescription>
                      </div>
                    </div>
                  </CardHeader>
                </Card>

                {currentWeek.strand && (
                  <Card className="mb-4">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm text-muted-foreground">Strand</CardTitle>
                    </CardHeader>
                    <CardContent className="pt-0">
                      <p className="text-lg font-semibold">{currentWeek.strand}</p>
                      {currentWeek.sub_strand && (
                        <p className="text-sm text-muted-foreground mt-1">
                          <span className="font-medium">Sub-strand:</span> {currentWeek.sub_strand}
                        </p>
                      )}
                    </CardContent>
                  </Card>
                )}

                {currentWeek.content_standards.length > 0 && (
                  <Card className="mb-4">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">Content Standards</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2">
                        {currentWeek.content_standards.map((cs, idx) => (
                          <div key={idx} className="p-2 bg-muted rounded text-sm">{cs}</div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {currentWeek.indicators.length > 0 && (
                  <Card className="mb-4">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">Indicators</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2">
                        {currentWeek.indicators.map((ind, idx) => (
                          <div key={idx} className="p-2 bg-muted rounded text-sm">{ind}</div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {currentWeek.resources.length > 0 && (
                  <Card className="mb-4">
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">Resources</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex flex-wrap gap-2">
                        {currentWeek.resources.map((res, idx) => (
                          <span key={idx} className="px-2 py-1 bg-secondary rounded text-sm">{res}</span>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Navigation + Actions */}
                <div className="flex flex-col sm:flex-row justify-between gap-4 mt-6">
                  <div className="flex flex-wrap gap-2">
                    {selectedWeek > weeks[0]?.week_number && (
                      <Button variant="outline" onClick={() => setSelectedWeek(selectedWeek - 1)}>
                        <ArrowLeft className="h-4 w-4 mr-2" /> Previous
                      </Button>
                    )}
                    {selectedWeek < weeks[weeks.length - 1]?.week_number && (
                      <Button variant="outline" onClick={() => setSelectedWeek(selectedWeek + 1)}>
                        Next <ArrowRight className="h-4 w-4 ml-2" />
                      </Button>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Link href="/dashboard">
                      <Button variant="outline">Back to Dashboard</Button>
                    </Link>
                    <Button onClick={handleApprove} disabled={approving} size="lg">
                      <CheckCircle className="h-4 w-4 mr-2" />
                      {approving ? 'Approving...' : 'Approve & Configure'}
                    </Button>
                  </div>
                </div>
              </>
            ) : null}
          </div>
        </div>
      </main>
    </div>
  )
}
