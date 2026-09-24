'use client'

import { useState, useEffect, type ReactNode } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { StatusPill } from '@/components/ui/badge'
import { Banner } from '@/components/ui/banner'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { PageHeader } from '@/components/ui/page-header'
import { Users, Key, UserPlus } from 'lucide-react'
import { api } from '@/lib/api'

interface DashboardData {
  school: { id: string; name: string; school_code: string; status: string } | null
  license: {
    status: string
    plan: string | null
    start_date: string | null
    expiry_date: string | null
    seat_limit: number
  } | null
  teachers: any[]
  seats: { used: number; limit: number }
}

export default function SchoolAdminDashboard() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    load()
  }, [])

  const load = async () => {
    try {
      setLoading(true)
      setError(null)
      setData(await api.getMySchool())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load school data')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  if (error) {
    return (
      <SurfaceCard className="p-8 text-center">
        <p className="mb-4 text-destructive">{error}</p>
        <Button onClick={load}>Try Again</Button>
      </SurfaceCard>
    )
  }

  const teacherCount = data?.teachers?.length || 0
  const lic = data?.license
  const restricted = !lic || lic.status !== 'active'
  const recentTeachers = (data?.teachers || []).slice(0, 5)

  const stat = (label: string, value: ReactNode) => (
    <SurfaceCard className="px-5 py-4">
      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{label}</p>
      <div className="mt-1.5 text-2xl font-bold text-[#102A43]">{value}</div>
    </SurfaceCard>
  )

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="School admin"
        title={data?.school?.name || 'School Dashboard'}
        description={<>{data?.school?.school_code} &bull; {lic?.plan || 'No plan'}</>}
        actions={
          <>
            <Link href="/school-admin/teachers">
              <Button>
                <UserPlus className="mr-1.5 h-4 w-4" />
                Add Teacher
              </Button>
            </Link>
            <Link href="/school-admin/license">
              <Button variant="outline">
                <Key className="mr-1.5 h-4 w-4" />
                License
              </Button>
            </Link>
          </>
        }
      />

      {restricted && (
        <Banner tone="warning" title={lic ? `License ${lic.status}` : 'No active license'}>
          Teacher access and new teacher accounts are restricted until the school license is
          active. Your school data is preserved. Contact SchemeKnit to renew.
        </Banner>
      )}

      {/* ── At a glance ─────────────────────────────────────────────── */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stat('Teachers', teacherCount)}
        {stat('Seats used', `${data?.seats.used ?? 0} / ${data?.seats.limit ?? 0}`)}
        {stat(
          'License status',
          <StatusPill tone={lic?.status === 'active' ? 'success' : 'caution'} className="capitalize">
            {lic?.status || 'none'}
          </StatusPill>,
        )}
        {stat('License expiry', lic?.expiry_date || '—')}
      </div>

      {/* ── Next actions ────────────────────────────────────────────── */}
      <div className="grid gap-4 md:grid-cols-2">
        <SurfaceCard className="flex items-center justify-between gap-4 px-5 py-5">
          <div>
            <p className="font-semibold text-[#102A43]">Manage your teaching staff</p>
            <p className="text-sm text-muted-foreground">Add teachers, manage access, reset passwords</p>
          </div>
          <Link href="/school-admin/teachers" className="shrink-0">
            <Button>
              <Users className="mr-1.5 h-4 w-4" />
              Teachers
            </Button>
          </Link>
        </SurfaceCard>
        <SurfaceCard className="flex items-center justify-between gap-4 px-5 py-5">
          <div>
            <p className="font-semibold text-[#102A43]">License &amp; entitlement</p>
            <p className="text-sm text-muted-foreground">Plan, seats, expiry, activation status</p>
          </div>
          <Link href="/school-admin/license" className="shrink-0">
            <Button variant="outline">
              <Key className="mr-1.5 h-4 w-4" />
              License
            </Button>
          </Link>
        </SurfaceCard>
      </div>

      {/* ── Recent teachers ─────────────────────────────────────────── */}
      <SurfaceCard data-recent-teachers className="px-5 py-5 sm:px-6">
        <div className="flex items-baseline justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-[#102A43]">Recent Teachers</h2>
            <p className="text-sm text-muted-foreground">Latest teacher accounts in this school</p>
          </div>
          <Link href="/school-admin/teachers" className="text-sm font-medium text-[#04769B] hover:underline">
            View all
          </Link>
        </div>
        <div className="mt-4">
          {!recentTeachers.length ? (
            <div className="py-6 text-center">
              <p className="mb-1 font-medium">No teachers yet</p>
              <p className="mb-4 text-sm text-muted-foreground">
                Add your first teacher to get started with lesson planning.
              </p>
              <Link href="/school-admin/teachers">
                <Button size="sm">Add Teacher</Button>
              </Link>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/50 hover:bg-muted/50">
                  <TableHead>Name</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead className="text-right">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recentTeachers.map((t: any) => (
                  <TableRow key={t.id}>
                    <TableCell className="font-medium">{t.full_name}</TableCell>
                    <TableCell className="text-muted-foreground">{t.email}</TableCell>
                    <TableCell className="text-right">
                      <StatusPill tone={t.is_active ? 'success' : 'danger'}>
                        {t.is_active ? 'active' : 'inactive'}
                      </StatusPill>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      </SurfaceCard>
    </div>
  )
}
