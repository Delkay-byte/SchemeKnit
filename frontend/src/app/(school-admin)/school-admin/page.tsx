'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { StatusPill } from '@/components/ui/badge'
import { Building2, Users, Key, AlertTriangle, UserPlus } from 'lucide-react'
import { api } from '@/lib/api'
import { PageHeader } from '@/components/ui/page-header'

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
      <Card>
        <CardContent className="p-8 text-center">
          <p className="text-destructive mb-4">{error}</p>
          <Button onClick={load}>Try Again</Button>
        </CardContent>
      </Card>
    )
  }

  const teacherCount = data?.teachers?.length || 0
  const lic = data?.license
  const restricted = !lic || lic.status !== 'active'

  return (
    <div className="space-y-6">
      <PageHeader
        title={
          <span className="flex items-center gap-2">
            <Building2 className="h-6 w-6" aria-hidden="true" />
            {data?.school?.name || 'School Dashboard'}
          </span>
        }
        description={<>{data?.school?.school_code} &bull; {lic?.plan || 'No plan'}</>}
      />

      {restricted && (
        <Card className="border-orange-300 bg-orange-50">
          <CardContent className="p-4 flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-orange-600 mt-0.5" />
            <div className="text-sm">
              <p className="font-medium text-orange-800">
                {lic ? `License ${lic.status}` : 'No active license'}
              </p>
              <p className="text-orange-700">
                Teacher access and new teacher accounts are restricted until the school license is
                active. Your school data is preserved. Contact SchemeKnit to renew.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground">Teachers</p>
            <p className="text-2xl font-bold">{teacherCount}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground">Seats Used</p>
            <p className="text-2xl font-bold">
              {data?.seats.used ?? 0} / {data?.seats.limit ?? 0}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground">License Status</p>
            <p className="text-2xl font-bold capitalize">{lic?.status || 'None'}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-muted-foreground">License Expiry</p>
            <p className="text-2xl font-bold">{lic?.expiry_date || '—'}</p>
          </CardContent>
        </Card>
        <Card className="md:col-span-2">
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <p className="font-medium">Manage your teaching staff</p>
              <p className="text-sm text-muted-foreground">Add teachers, manage access, reset passwords</p>
            </div>
            <Link href="/school-admin/teachers">
              <Button>
                <UserPlus className="h-4 w-4 mr-1.5" />
                Teachers
              </Button>
            </Link>
          </CardContent>
        </Card>
        <Card className="md:col-span-2">
          <CardContent className="p-4 flex items-center justify-between">
            <div>
              <p className="font-medium">License &amp; entitlement</p>
              <p className="text-sm text-muted-foreground">Plan, seats, expiry, activation status</p>
            </div>
            <Link href="/school-admin/license">
              <Button variant="outline">
                <Key className="h-4 w-4 mr-1.5" />
                License
              </Button>
            </Link>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Users className="h-5 w-5" /> Recent Teachers
          </CardTitle>
          <CardDescription>Latest teacher accounts in this school</CardDescription>
        </CardHeader>
        <CardContent>
          {!data?.teachers?.length ? (
            <div className="text-center py-6">
              <p className="font-medium mb-1">No teachers yet</p>
              <p className="text-sm text-muted-foreground mb-4">
                Add your first teacher to get started with lesson planning.
              </p>
              <Link href="/school-admin/teachers">
                <Button size="sm">Add Teacher</Button>
              </Link>
            </div>
          ) : (
            <div className="space-y-1">
              {data.teachers.slice(0, 5).map((t: any) => (
                <div key={t.id} className="flex items-center justify-between text-sm border rounded p-2">
                  <span>{t.full_name} &lt;{t.email}&gt;</span>
                  <StatusPill tone={t.is_active ? 'success' : 'danger'}>
                    {t.is_active ? 'active' : 'inactive'}
                  </StatusPill>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
