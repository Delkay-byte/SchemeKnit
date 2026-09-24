'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { StatusPill } from '@/components/ui/badge'
import { Key, AlertTriangle, CheckCircle } from 'lucide-react'
import { api } from '@/lib/api'
import { PageHeader } from '@/components/ui/page-header'

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
      <Card>
        <CardContent className="p-8 text-center">
          <p className="text-destructive mb-4">{error}</p>
          <Button onClick={load}>Try Again</Button>
        </CardContent>
      </Card>
    )
  }

  const lic = data?.license
  const active = lic?.status === 'active'

  return (
    <div className="max-w-2xl space-y-4">
      <PageHeader
        title={
          <span className="flex items-center gap-2">
            <Key className="h-6 w-6" aria-hidden="true" />
            License &amp; Entitlement
          </span>
        }
      />

      {!lic ? (
        <Card className="border-orange-300 bg-orange-50">
          <CardContent className="p-6 text-center">
            <AlertTriangle className="h-10 w-10 text-orange-600 mx-auto mb-3" />
            <p className="font-medium mb-1">No license found</p>
            <p className="text-sm text-muted-foreground">
              This school has no license on record. Contact SchemeKnit to activate
              your subscription. Existing school data is preserved.
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              {active
                ? <CheckCircle className="h-5 w-5 text-green-600" />
                : <AlertTriangle className="h-5 w-5 text-orange-600" />}
              {lic.plan || 'School License'}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex justify-between border-b py-2">
              <span className="text-muted-foreground">Status</span>
              <StatusPill tone={active ? 'success' : 'caution'}>
                {lic.status}
              </StatusPill>
            </div>
            <div className="flex justify-between border-b py-2">
              <span className="text-muted-foreground">Teacher seats</span>
              <span className="font-medium">{data?.seats?.used ?? 0} of {lic.seat_limit ?? 0} used</span>
            </div>
            <div className="flex justify-between border-b py-2">
              <span className="text-muted-foreground">Start date</span>
              <span className="font-medium">{lic.start_date || '—'}</span>
            </div>
            <div className="flex justify-between border-b py-2">
              <span className="text-muted-foreground">Expiry date</span>
              <span className="font-medium">{lic.expiry_date || '—'}</span>
            </div>
            {!active && (
              <p className="text-sm text-orange-700 bg-orange-50 border border-orange-200 rounded p-3">
                This license is {lic.status}. Teacher lesson planning and new teacher
                accounts are restricted until renewal. All school and teacher data is preserved.
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              Only active teachers consume seats. Plan changes and renewals are handled
              by SchemeKnit — contact support.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
