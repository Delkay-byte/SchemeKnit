'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { FileText, Eye, Download, ArrowLeft, BookOpen } from 'lucide-react'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { Header } from '@/components/header'

interface LessonPlan {
  id: string
  scheme_id: string
  scheme_filename: string
  scheme_subject: string
  week_number: number
  lesson_date: string | null
  lesson_number: number
  lesson_topic: string
  strand: string
  sub_strand: string
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
    <div className="min-h-screen bg-background">
      <Header />
      <main className="container mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <BookOpen className="h-6 w-6" />
              Lesson Plans
            </h1>
            <p className="text-muted-foreground mt-1">
              {lessons.length === 0
                ? 'No lesson plans yet. Generate some from a scheme.'
                : `${lessons.length} lesson plan${lessons.length !== 1 ? 's' : ''} across ${uniqueSchemes.length} scheme${uniqueSchemes.length !== 1 ? 's' : ''}`
              }
            </p>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        ) : error ? (
          <Card>
            <CardContent className="p-8 text-center">
              <p className="text-destructive mb-4">{error}</p>
              <Button onClick={loadLessons}>Try Again</Button>
            </CardContent>
          </Card>
        ) : lessons.length === 0 ? (
          <Card>
            <CardContent className="p-12 text-center">
              <BookOpen className="h-16 w-16 text-muted-foreground mx-auto mb-4" />
              <p className="text-lg font-medium mb-2">No lesson plans yet</p>
              <p className="text-muted-foreground">
                Upload a scheme, review it, then generate lesson plans to see them here.
              </p>
            </CardContent>
          </Card>
        ) : (
          <>
            {/* Filter by scheme */}
            {uniqueSchemes.length > 1 && (
              <div className="mb-4">
                <select
                  value={filterScheme}
                  onChange={(e) => setFilterScheme(e.target.value)}
                  className="px-3 py-2 border rounded-lg text-sm"
                >
                  <option value="">All Schemes</option>
                  {uniqueSchemes.map(s => (
                    <option key={s.id} value={s.id}>{s.filename} ({s.subject})</option>
                  ))}
                </select>
              </div>
            )}

            {/* Lessons Table */}
            <Card>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-muted/50">
                        <th className="text-left p-3 font-medium">Week</th>
                        <th className="text-left p-3 font-medium">Lesson</th>
                        <th className="text-left p-3 font-medium">Date</th>
                        <th className="text-left p-3 font-medium">Topic</th>
                        <th className="text-left p-3 font-medium">Scheme</th>
                        <th className="text-left p-3 font-medium">Status</th>
                        <th className="text-right p-3 font-medium">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredLessons.map((lesson) => (
                        <tr key={lesson.id} className="border-b hover:bg-muted/30">
                          <td className="p-3">Week {lesson.week_number}</td>
                          <td className="p-3">{lesson.lesson_number}</td>
                          <td className="p-3">{lesson.lesson_date || 'TBD'}</td>
                          <td className="p-3 max-w-[200px] truncate">{lesson.lesson_topic || 'Untitled'}</td>
                          <td className="p-3 max-w-[150px] truncate text-muted-foreground">{lesson.scheme_filename}</td>
                          <td className="p-3">
                            <span className={`px-2 py-0.5 rounded-full text-xs ${
                              lesson.status === 'generated' ? 'bg-green-100 text-green-800' :
                              lesson.status === 'edited' ? 'bg-blue-100 text-blue-800' :
                              'bg-gray-100 text-gray-800'
                            }`}>
                              {lesson.teacher_edited ? 'Edited' : lesson.status}
                            </span>
                          </td>
                          <td className="p-3 text-right">
                            <div className="flex justify-end gap-1">
                              <Link href={`/lessons/${lesson.id}`}>
                                <Button size="sm" variant="ghost">
                                  <Eye className="h-4 w-4 mr-1" />
                                  Open
                                </Button>
                              </Link>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </main>
    </div>
  )
}
