'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
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
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
      </div>
    )
  }

  const isAlreadyPro = plan && (plan.edition === 'teacher' || plan.edition === 'school') && plan.is_active

  return (
    <div className="min-h-screen">
      <main className="container mx-auto px-4 py-8 max-w-2xl">
        <Link href="/dashboard" className="mb-6 inline-flex items-center text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="mr-1 h-4 w-4" />
          Back to Dashboard
        </Link>

        <div className="mb-8">
          <PageHeader
            eyebrow="Upgrade"
            title="Upgrade to Teacher Pro"
            description="Unlock the full power of SchemeKnit for independent teaching."
          />
        </div>

        {isAlreadyPro ? (
          <SurfaceCard
            data-already-pro
            accent="bg-gradient-to-r from-[#102A43] to-[#04A9CE]"
            className="px-6 py-8 text-center"
          >
            <h2 className="mb-2 text-xl font-semibold text-[#102A43]">
              You already have Teacher Pro!
            </h2>
            <p className="mb-4 text-muted-foreground">
              Your plan includes unlimited generations, batch processing, and more.
            </p>
            <Button asChild>
              <Link href="/dashboard">Go to Dashboard</Link>
            </Button>
          </SurfaceCard>
        ) : (
          <>
            <SurfaceCard
              data-pro-features
              accent="bg-gradient-to-r from-[#102A43] to-[#04A9CE]"
              className="px-6 py-6"
            >
              <h2 className="text-lg font-semibold text-[#102A43]">Teacher Pro Features</h2>
              <ul className="mt-4 space-y-3">
                {PRO_FEATURES.map((feature) => (
                  <li key={feature} className="flex items-start gap-3">
                    <Check className="mt-0.5 h-5 w-5 shrink-0 text-[#04A9CE]" aria-hidden="true" />
                    <span className="text-sm">{feature}</span>
                  </li>
                ))}
              </ul>
            </SurfaceCard>

            <SurfaceCard data-upgrade-cta className="mt-6 px-6 py-6 text-center">
              <p className="mb-4 text-muted-foreground">
                Teacher Pro is available through your school administrator
                or as an individual subscription.
              </p>
              <div className="flex flex-col justify-center gap-3 sm:flex-row">
                <Button asChild>
                  <Link href="/payments">View Plans &amp; Payments</Link>
                </Button>
                <Button asChild variant="outline">
                  <Link href="/dashboard">Maybe Later</Link>
                </Button>
              </div>
            </SurfaceCard>
          </>
        )}
      </main>
    </div>
  )
}
