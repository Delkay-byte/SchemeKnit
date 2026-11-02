'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

// Legacy alias: the School Admin workspace lives at /school-admin.
export default function AdminAliasPage() {
  const router = useRouter()
  useEffect(() => {
    router.replace('/school-admin')
  }, [router])
  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
        Taking you to the school administrator workspace…
      </p>
    </div>
  )
}
