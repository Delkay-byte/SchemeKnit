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
    <div className="min-h-screen bg-background flex items-center justify-center">
      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
    </div>
  )
}
