'use client'

import { useState, useEffect, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { StatusPill } from '@/components/ui/badge'
import { PageHeader } from '@/components/ui/page-header'
import { AlertTriangle, CheckCircle } from 'lucide-react'
import { api } from '@/lib/api'

export default function SchoolLicensePage() {
  const [data, setData] = useState<any>(null)
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
      setError(err instanceof Error ? err.message : 'Failed to load license')
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

  const lic = data?.license
  const active = lic?.status === 'active'

  const detailRow = (label: string, value: ReactNode) => (
    <div className="flex items-center justify-between border-b border-[#102A43]/8 py-2.5 last:border-b-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium text-[#102A43]">{value}</span>
    </div>
  )

  return (
    <div className="max-w-2xl space-y-4">
      <PageHeader
        eyebrow="School admin"
        title="License and entitlement"
        description="Plan, teacher seats and activation status for this school."
      />

      {!lic ? (
        <SurfaceCard accent="bg-amber-400" className="px-6 py-8 text-center">
          <AlertTriangle className="mx-auto mb-3 h-10 w-10 text-amber-600" aria-hidden="true" />
          <p className="mb-1 font-medium text-[#102A43]">No license found</p>
          <p className="text-sm text-muted-foreground">
            This school has no license on record. Contact SchemeKnit to activate
            your subscription. Existing school data is preserved.
          </p>
        </SurfaceCard>
      ) : (
        <SurfaceCard
          data-license-card
          accent={active ? 'bg-gradient-to-r from-[#102A43] to-[#04A9CE]' : 'bg-amber-400'}
          className="px-5 py-5 sm:px-6"
        >
          <div className="flex items-center gap-2">
            {active ? (
              <CheckCircle className="h-5 w-5 text-green-600" aria-hidden="true" />
            ) : (
              <AlertTriangle className="h-5 w-5 text-amber-600" aria-hidden="true" />
            )}
            <h2 className="text-lg font-semibold text-[#102A43]">{lic.plan || 'School License'}</h2>
          </div>

          <div className="mt-3">
            {detailRow('Status', (
              <StatusPill tone={active ? 'success' : 'caution'}>{lic.status}</StatusPill>
            ))}
            {detailRow('Teacher seats', `${data?.seats?.used ?? 0} of ${lic.seat_limit ?? 0} used`)}
            {detailRow('Start date', lic.start_date || '—')}
            {detailRow('Expiry date', lic.expiry_date || '—')}
          </div>

          {!active && (
            <p className="mt-4 rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              This license is {lic.status}. Teacher lesson planning and new teacher
              accounts are restricted until renewal. All school and teacher data is preserved.
            </p>
          )}

          <p className="mt-4 text-xs text-muted-foreground">
            Only active teachers consume seats. Plan changes and renewals are handled
            by SchemeKnit — contact support.
          </p>
        </SurfaceCard>
      )}
    </div>
  )
}
