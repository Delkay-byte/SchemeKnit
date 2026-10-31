'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { ShieldCheck } from 'lucide-react'

/** Server-side revoke-all for lost or shared devices. */
export function SessionSecurityCard() {
  const router = useRouter()
  const { logout } = useAuth()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const revokeAll = async () => {
    if (!window.confirm('Sign out every device, including this one?')) return
    setLoading(true)
    setError('')
    try {
      await api.logoutAll()
      logout()
      router.push('/login')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not revoke sessions')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-muted-foreground" />
          <div>
            <CardTitle className="text-lg">Session Security</CardTitle>
            <CardDescription>
              Revoke every active session if a device is lost or shared.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {error && <p className="mb-3 text-sm text-destructive">{error}</p>}
        <Button variant="outline" onClick={revokeAll} disabled={loading}>
          {loading ? 'Revoking…' : 'Sign out all devices'}
        </Button>
      </CardContent>
    </Card>
  )
}
