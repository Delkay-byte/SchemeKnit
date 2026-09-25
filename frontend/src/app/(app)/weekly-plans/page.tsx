'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { CalendarDays, Plus, FolderOpen } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { Banner } from '@/components/ui/banner'
import { PageHeader } from '@/components/ui/page-header'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/table'
import { api } from '@/lib/api'
import type { WeeklyPlanListItem } from '@/types'

/**
 * Weekly class-teacher plans (Approved WAPEF Basic 1-3 Plan).
 *
 * One saved weekly plan holds every subject section of the class, so the
 * list is one row per WEEK (not one row per lesson): class, week, term and
 * the subjects the teacher scheduled. Basic 4-JHS plans are generated from
 * the subject-teacher Approved WAPEF Plan and never appear here.
 */
export default function WeeklyPlansPage() {
  const [plans, setPlans] = useState<WeeklyPlanListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const response = await api.listWeeklyPlans()
        if (!cancelled) setPlans(response.plans || [])
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load weekly plans')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [])

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Weekly Plan"
        title="Weekly Class Plans"
        description="Basic 1-3 class-teacher weekly plans: one document holding every subject section with its own DAYS | STARTER | MAIN | REFLECTION table."
        actions={
          <Button asChild>
            <Link href="/weekly-plans/new">
              <Plus className="h-4 w-4" aria-hidden="true" />
              New weekly plan
            </Link>
          </Button>
        }
      />

      {error && (
        <Banner tone="danger" title="Could not load weekly plans">{error}</Banner>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12" data-weekly-loading>
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary" />
        </div>
      ) : plans.length === 0 ? (
        <SurfaceCard data-empty className="p-10 text-center">
          <CalendarDays className="mx-auto h-10 w-10 text-muted-foreground" aria-hidden="true" />
          <h2 className="mt-3 text-lg font-semibold">No weekly plans yet</h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Build your first Basic 1-3 weekly plan: pick the subjects you teach,
            assign their teaching days, and generate one weekly document.
          </p>
          <Button asChild className="mt-4">
            <Link href="/weekly-plans/new">
              <Plus className="h-4 w-4" aria-hidden="true" />
              New weekly plan
            </Link>
          </Button>
        </SurfaceCard>
      ) : (
        <SurfaceCard data-weekly-list className="p-0 overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Class</TableHead>
                <TableHead>Week</TableHead>
                <TableHead>Term</TableHead>
                <TableHead>Subjects</TableHead>
                <TableHead>Updated</TableHead>
                <TableHead><span className="sr-only">Actions</span></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {plans.map((plan) => (
                <TableRow key={plan.id}>
                  <TableCell className="font-medium">{plan.class_level}</TableCell>
                  <TableCell>Week {plan.week_number}</TableCell>
                  <TableCell>{plan.term}</TableCell>
                  <TableCell className="max-w-[18rem] truncate text-muted-foreground">
                    {(plan.subjects || []).join(', ')}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {String(plan.updated_date || '').slice(0, 10)}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="outline" size="sm" asChild>
                      <Link href={`/weekly-plans/${plan.id}`}>
                        <FolderOpen className="h-4 w-4" aria-hidden="true" />
                        Open
                      </Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </SurfaceCard>
      )}
    </div>
  )
}
