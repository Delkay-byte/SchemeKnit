'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { Select } from '@/components/ui/select'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { StatusPill } from '@/components/ui/badge'
import { PageHeader } from '@/components/ui/page-header'
import { Eye, BookOpen } from 'lucide-react'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'

interface LessonPlan {
  id: string
  scheme_id: string
  scheme_filename: string
  scheme_subject: string
  week_number: number
  teaching_week?: number
  carry_forward?: boolean
  lesson_date: string | null
  lesson_number: string | number
  lesson_sequence?: number
  lesson_topic: string
  strand: string
  sub_strand: string
  period?: string
  indicators?: string[]
  indicator_codes?: string[]
  class_level: string
  subject: string
  status: string
  teacher_edited: boolean
  job_id: string
}

export default function LessonsPage() {
  const router = useRouter()
  const { user, loading: authLoading } = useAuth()
  const [lessons, setLessons] = useState<LessonPlan[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filterScheme, setFilterScheme] = useState<string>('')

  useEffect(() => {
    if (!authLoading && !user) {
      router.push('/login')
      return
    }
    if (user) {
      loadLessons()
    }
  }, [user, authLoading])

  const loadLessons = async () => {
    try {
      setLoading(true)
      const response = await api.listAllLessons()
      setLessons(response.lesson_plans || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load lesson plans')
    } finally {
      setLoading(false)
    }
  }

  const filteredLessons = filterScheme
    ? lessons.filter(l => l.scheme_id === filterScheme)
    : lessons

  const uniqueSchemes = Array.from(
    new Map(lessons.map(l => [l.scheme_id, { id: l.scheme_id, filename: l.scheme_filename, subject: l.scheme_subject }])).values()
  )

  if (authLoading || !user) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <main className="container mx-auto px-4 py-8">
        <div className="mb-6">
          <PageHeader
            title={
              <span className="flex items-center gap-2">
                <BookOpen className="h-6 w-6" aria-hidden="true" />
                Lesson Plans
              </span>
            }
            description={
              lessons.length === 0
                ? 'No lesson plans yet. Generate some from a scheme.'
                : `${lessons.length} lesson plan${lessons.length !== 1 ? 's' : ''} across ${uniqueSchemes.length} scheme${uniqueSchemes.length !== 1 ? 's' : ''}`
            }
            actions={
              <Button variant="outline" asChild>
                <Link href="/upload">Upload scheme</Link>
              </Button>
            }
          />
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        ) : error ? (
          <SurfaceCard className="px-6 py-8 text-center">
            <p className="mb-4 text-destructive">{error}</p>
            <Button onClick={loadLessons}>Try Again</Button>
          </SurfaceCard>
        ) : lessons.length === 0 ? (
          <SurfaceCard data-empty className="px-6 py-12 text-center">
            <BookOpen className="mx-auto mb-4 h-12 w-12 text-slate-300" aria-hidden="true" />
            <p className="text-lg font-medium text-[#102A43]">No lesson plans yet</p>
            <p className="mt-1 text-muted-foreground">
              Upload a scheme, review it, then generate lesson plans to see them here.
            </p>
            <div className="mt-5 flex flex-wrap justify-center gap-3">
              <Button asChild>
                <Link href="/upload">Upload Scheme</Link>
              </Button>
              <Button variant="outline" asChild>
                <Link href="/dashboard">Go to Dashboard</Link>
              </Button>
            </div>
          </SurfaceCard>
        ) : (
          <>
            {/* Filter by scheme */}
            {uniqueSchemes.length > 1 && (
              <div className="mb-4">
                <Select
                  value={filterScheme}
                  onChange={(e) => setFilterScheme(e.target.value)}
                  className="w-auto"
                  aria-label="Filter by scheme"
                >
                  <option value="">All Schemes</option>
                  {uniqueSchemes.map(s => (
                    <option key={s.id} value={s.id}>{s.filename} ({s.subject})</option>
                  ))}
                </Select>
              </div>
            )}

            {/* Lessons table — one row per lesson, status at a glance. */}
            <SurfaceCard data-lessons-table className="overflow-hidden">
              <Table className="min-w-[860px]">
                <TableHeader>
                  <TableRow className="bg-muted/50 hover:bg-muted/50">
                    <TableHead>Subject</TableHead>
                    <TableHead>Indicator</TableHead>
                    <TableHead>Week</TableHead>
                    <TableHead>Teaching Period</TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredLessons.map((lesson) => {
                    const teachingWeek = lesson.teaching_week || lesson.week_number
                    return (
                      <TableRow key={lesson.id} className="hover:bg-muted/30">
                        <TableCell className="whitespace-nowrap font-medium">
                          {lesson.subject || lesson.scheme_subject}
                        </TableCell>
                        <TableCell className="max-w-[260px]">
                          <span className="block font-mono text-xs text-[#04769B]">
                            {lesson.indicator_codes?.[0] ||
                              (lesson.strand ? lesson.strand.slice(0, 18) : '—')}
                          </span>
                          <span
                            className="block truncate text-xs text-muted-foreground"
                            title={lesson.indicators?.[0] || lesson.sub_strand || ''}
                          >
                            {lesson.indicators?.[0] || lesson.sub_strand || lesson.strand || ''}
                          </span>
                        </TableCell>
                        <TableCell className="whitespace-nowrap">
                          W{teachingWeek}
                          {lesson.carry_forward && lesson.week_number !== teachingWeek && (
                            <span className="block text-[11px] text-muted-foreground">
                              from W{lesson.week_number}
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="whitespace-nowrap">
                          {lesson.period || '—'}
                        </TableCell>
                        <TableCell className="whitespace-nowrap">
                          {lesson.lesson_date || 'TBD'}
                        </TableCell>
                        <TableCell>
                          <StatusPill
                            tone={
                              lesson.status === 'generated' ? 'success' :
                              lesson.status === 'edited' ? 'info' : 'neutral'
                            }
                          >
                            {lesson.teacher_edited ? 'Edited' : lesson.status}
                          </StatusPill>
                        </TableCell>
                        <TableCell className="text-right">
                          <div className="flex justify-end gap-1">
                            <Button size="sm" variant="ghost" asChild>
                              <Link href={`/lessons/${lesson.id}`}>
                                <Eye className="mr-1 h-4 w-4" />
                                Open
                              </Link>
                            </Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </SurfaceCard>
          </>
        )}
      </main>
    </div>
  )
}
