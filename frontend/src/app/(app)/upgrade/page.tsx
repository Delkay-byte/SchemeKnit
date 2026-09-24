'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Check, ArrowLeft } from 'lucide-react'
import { useAuth } from '@/lib/auth-context'
import { PageHeader } from '@/components/ui/page-header'
import { PlanResolution } from '@/types'
import { api } from '@/lib/api'

const PRO_FEATURES = [
  'Unlimited individual lesson generations',
  'Full batch generation for entire terms',
  'Download complete terms as ZIP archives',
  'PDF export of all plans',
  '10 custom templates',
  '100 lesson history',
  '50 AI credits for lesson assistance',
  'Advanced analytics dashboard',
  'Priority feature access',
]

export default function UpgradePage() {
  const router = useRouter()
  const { user, loading: authLoading } = useAuth()
  const [plan, setPlan] = useState<PlanResolution | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!authLoading && !user) {
      router.push('/login')
      return
    }
    if (user) {
      api.getMyPlan()
        .then(setPlan)
        .catch(() => {})
        .finally(() => setLoading(false))
    }
  }, [user, authLoading])

  if (authLoading || !user) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    )
  }

  const isAlreadyPro = plan && (plan.edition === 'teacher' || plan.edition === 'school') && plan.is_active

  return (
    <div className="min-h-screen">
      <main className="container mx-auto px-4 py-8 max-w-2xl">
        <Link href="/dashboard" className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-6">
          <ArrowLeft className="h-4 w-4 mr-1" />
          Back to Dashboard
        </Link>

        <div className="mb-8">
          <PageHeader
            title="Upgrade to Teacher Pro"
            description="Unlock the full power of SchemeKnit for independent teaching."
          />
        </div>

        {isAlreadyPro ? (
          <Card className="border-emerald-200 bg-emerald-50">
            <CardContent className="p-8 text-center">
              <h2 className="text-xl font-semibold text-emerald-800 mb-2">
                You already have Teacher Pro!
              </h2>
              <p className="text-emerald-700 mb-4">
                Your plan includes unlimited generations, batch processing, and more.
              </p>
              <Button asChild className="bg-emerald-600 hover:bg-emerald-700">
                <Link href="/dashboard">Go to Dashboard</Link>
              </Button>
            </CardContent>
          </Card>
        ) : (
          <>
            <Card className="mb-8">
              <CardHeader>
                <CardTitle className="text-emerald-700">Teacher Pro Features</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-3">
                  {PRO_FEATURES.map((feature) => (
                    <li key={feature} className="flex items-start gap-3">
                      <Check className="h-5 w-5 text-emerald-500 mt-0.5 shrink-0" />
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>

            <Card className="border-emerald-300">
              <CardContent className="p-6 text-center">
                <p className="text-muted-foreground mb-4">
                  Teacher Pro is available through your school administrator
                  or as an individual subscription.
                </p>
                <div className="flex flex-col sm:flex-row gap-3 justify-center">
                  <Button asChild className="bg-emerald-600 hover:bg-emerald-700">
                    <Link href="/login/school-admin">Contact School Admin</Link>
                  </Button>
                  <Button asChild variant="outline">
                    <Link href="/dashboard">Maybe Later</Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </main>
    </div>
  )
}
