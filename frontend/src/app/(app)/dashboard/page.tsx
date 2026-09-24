'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field } from '@/components/ui/field'
import { StatusFromKey, StatusPill } from '@/components/ui/badge'
import { SurfaceCard } from '@/components/ui/surface-card'
import { Banner } from '@/components/ui/banner'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/ui/dialog'
import { FileText, Eye, Play, BookOpen, Trash2, Crown, Zap, School, Upload } from 'lucide-react'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { PageHeader } from '@/components/ui/page-header'
import { SchemeOfWork, PlanResolution } from '@/types'

// Labels only — the server-persisted stage keys and the status fallback
// arrays below are unchanged (Batch 3 label set: the five steps teachers
// actually take through SchemeKnit).
const WORKFLOW_STEPS = [
  { label: 'Upload Scheme', status: ['uploaded'] },
  { label: 'Review Curriculum', status: ['extracted'] },
  { label: 'Select Indicators', status: ['approved'] },
  { label: 'Generate Lessons', status: ['generating'] },
  { label: 'Review & Export', status: ['generated', 'completed'] },
]

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <SurfaceCard data-stat className="px-4 py-4">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        {label}
      </p>
      <p className="mt-1 truncate text-2xl font-bold text-[#102A43]">{value}</p>
    </SurfaceCard>
  )
}

export default function Dashboard() {
  const router = useRouter()
  const { user, logout, loading: authLoading } = useAuth()
  const [schemes, setSchemes] = useState<SchemeOfWork[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [plan, setPlan] = useState<PlanResolution | null>(null)
  const [showActivateModal, setShowActivateModal] = useState(false)
  const [activationCode, setActivationCode] = useState('')
  const [activating, setActivating] = useState(false)
  // Server-persisted workflow stages for the active scheme (null = fallback to status).
  const [workflowStages, setWorkflowStages] = useState<{ key: string; state: string }[] | null>(null)
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)

  useEffect(() => {
    if (!authLoading && !user) {
      router.push('/login')
      return
    }
    if (user) {
      loadSchemes()
    }
  }, [user, authLoading])

  const loadSchemes = async () => {
    try {
      setLoading(true)
      const [schemesRes, planRes] = await Promise.all([
        api.listSchemes(),
        api.getMyPlan().catch(() => null),
      ])
      setSchemes(schemesRes.schemes || [])
      if (planRes) setPlan(planRes)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load schemes')
    } finally {
      setLoading(false)
    }
  }

  const handleActivateLicense = async () => {
    if (!activationCode.trim()) {
      setError('Please enter an activation code')
      return
    }
    setActivating(true)
    setError(null)
    try {
      await api.activateIndividualLicense(activationCode)
      setShowActivateModal(false)
      setActivationCode('')
      await loadSchemes() // Refresh plan
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Activation failed')
    } finally {
      setActivating(false)
    }
  }

  const getWorkflowStep = (status: string): number => {
    for (let i = 0; i < WORKFLOW_STEPS.length; i++) {
      if (WORKFLOW_STEPS[i].status.includes(status)) return i
    }
    return -1
  }

  const getNextAction = (scheme: SchemeOfWork): { label: string; href: string; icon: React.ReactNode } | null => {
    switch (scheme.status) {
      case 'uploaded':
      case 'extracted':
        return {
          label: 'Continue Review',
          href: `/review/${scheme.id}`,
          icon: <Eye className="h-4 w-4 mr-1.5" />,
        }
      case 'approved':
        return {
          label: 'Configure & Generate',
          href: `/generate/${scheme.id}`,
          icon: <Play className="h-4 w-4 mr-1.5" />,
        }
      case 'generated':
      case 'completed':
        return {
          label: 'View Lesson Plans',
          href: '/lessons',
          icon: <BookOpen className="h-4 w-4 mr-1.5" />,
        }
      default:
        return null
    }
  }

  const handleDelete = async (schemeId: string) => {
    try {
      setError(null)
      await api.deleteScheme(schemeId)
      setSchemes(schemes.filter(s => s.id !== schemeId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  const pendingSchemes = schemes.filter(s => s.status === 'uploaded' || s.status === 'extracted')
  const approvedSchemes = schemes.filter(s => s.status === 'approved')

  // The scheme whose workflow is shown: first pending, else first approved, else most recent.
  const activeScheme =
    pendingSchemes[0] || approvedSchemes[0] || schemes[0] || null
  const activeStep = activeScheme ? getWorkflowStep(activeScheme.status) : -1
  const activeSchemeId = activeScheme ? activeScheme.id : null

  // Persisted workflow state: fetched per active scheme, survives refresh/logout/reopen.
  // Falls back to status-derived steps if the endpoint is unreachable.
  // NOTE: kept above the auth early-return so hook order stays stable.
  useEffect(() => {
    if (!activeSchemeId) {
      setWorkflowStages(null)
      return
    }
    let cancelled = false
    api.getSchemeWorkflow(activeSchemeId)
      .then((res) => { if (!cancelled) setWorkflowStages(res.stages || null) })
      .catch(() => { if (!cancelled) setWorkflowStages(null) })
    return () => { cancelled = true }
  }, [activeSchemeId])

  if (authLoading || !user) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    )
  }

  const termLabel = (activeScheme || schemes[0])?.term?.trim() || '—'
  const remainingLabel =
    plan && plan.generation_limit > 0
      ? String(Math.max(plan.generation_limit - plan.generations_used, 0))
      : plan
        ? 'Unlimited'
        : '—'
  const primaryAction = activeScheme
    ? getNextAction(activeScheme)
    : { label: 'Upload Scheme', href: '/upload', icon: <Upload className="h-4 w-4 mr-1.5" /> }

  return (
    <div className="min-h-screen">
      <main className="container mx-auto px-4 py-8">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        ) : error ? (
          <Banner
            tone="danger"
            title="Something went wrong"
            action={
              <Button size="sm" variant="outline" onClick={loadSchemes}>
                Try Again
              </Button>
            }
          >
            {error}
          </Banner>
        ) : (
          <div className="space-y-6">
            {/* 1. Page header — one h1, one unmistakable primary action. */}
            <PageHeader
              title={`Welcome back, ${user.full_name?.split(' ')[0] || 'Teacher'}`}
              description={
                schemes.length === 0
                  ? 'Get started by uploading your first scheme of work.'
                  : `You have ${schemes.length} scheme${schemes.length !== 1 ? 's' : ''} in your workspace.`
              }
              actions={
                primaryAction ? (
                  <Button asChild>
                    <Link href={primaryAction.href}>
                      {primaryAction.icon}
                      {primaryAction.label}
                    </Link>
                  </Button>
                ) : null
              }
            />

            {/* 2. Term / context — stat cards, existing data only. */}
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <StatCard label="Active schemes" value={String(schemes.length)} />
              <StatCard
                label="Lesson plans this month"
                value={plan ? String(plan.generations_used) : '—'}
              />
              <StatCard label="Generations" value={remainingLabel} />
              <StatCard label="Current term" value={termLabel} />
            </div>

            {/* 3. Status — first-use profile prompt, then plan / entitlement. */}
            {/* First-use profile prompt (PART 18). The teacher's name is what
                the generated plan prints; when the profile has none yet we ask
                for it once here rather than falling back to a placeholder. The
                server still derives the name from the profile at generation. */}
            {user && !(user.full_name || '').trim() && (
              <Banner
                tone="info"
                title="Add your name to your profile"
                action={
                  <Button size="sm" asChild>
                    <Link href="/settings">Complete Profile</Link>
                  </Button>
                }
              >
                Your lesson plans are headed with the teacher name on your profile.
                Add it once so every plan is labelled correctly.
              </Banner>
            )}

            {/* Account surface — the badge reflects the resolved entitlement
                source (§13/§14). A school teacher sees SCHOOL ACCESS and is
                NOT pushed toward buying Individual Pro; an individual teacher
                sees FREE TEACHER / TEACHER PRO with an upgrade path. */}
            {plan && (
              <SurfaceCard
                data-plan
                accent="bg-gradient-to-r from-[#102A43] to-[#04769B]"
                className="px-5 py-5 sm:px-6"
              >
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div className="flex items-center gap-4">
                    <div className="rounded-full bg-[#04A9CE]/10 p-3 text-[#04769B]">
                      {plan.source === 'school' || plan.source === 'individual+school' ? (
                        <School className="h-5 w-5" />
                      ) : plan.edition === 'teacher' ? (
                        <Crown className="h-5 w-5" />
                      ) : (
                        <Zap className="h-5 w-5" />
                      )}
                    </div>
                    <div>
                      {plan.source === 'school' || plan.source === 'individual+school' ? (
                        <>
                          <StatusPill tone="success" className="mb-1 rounded text-[11px] font-bold uppercase tracking-wider">
                            School Access
                          </StatusPill>
                          <h3 className="font-semibold">
                            {plan.school_name || 'Your school'}
                          </h3>
                          <p className="text-sm text-muted-foreground">
                            Plan: {plan.plan_name}
                          </p>
                        </>
                      ) : plan.edition === 'teacher' ? (
                        <>
                          <StatusPill tone="info" className="mb-1 rounded text-[11px] font-bold uppercase tracking-wider">
                            Individual Teacher Pro
                          </StatusPill>
                          <h3 className="font-semibold">Teacher Pro</h3>
                          <p className="text-sm text-muted-foreground">
                            Individual subscription
                          </p>
                        </>
                      ) : (
                        <>
                          <StatusPill tone="neutral" className="mb-1 rounded text-[11px] font-bold uppercase tracking-wider">
                            Free Tier
                          </StatusPill>
                          <h3 className="font-semibold">Free Tier</h3>
                          <p className="text-sm text-muted-foreground">
                            Individual plan
                          </p>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-6 gap-y-3 text-sm text-muted-foreground">
                    <div className="text-center">
                      <div className="font-semibold text-foreground">
                        {plan.batch_generation ? 'Yes' : 'No'}
                      </div>
                      <div>Batch</div>
                    </div>
                    <div className="text-center">
                      <div className="font-semibold text-foreground">
                        {plan.ai_credits === 0
                          ? 'Unlimited'
                          : `${Math.max(plan.ai_credits - plan.ai_credits_used, 0)} / ${plan.ai_credits}`}
                      </div>
                      <div>
                        {plan.ai_lifetime ? 'AI generations (lifetime)' : 'AI generations remaining'}
                      </div>
                    </div>
                    {plan.edition === 'free' && plan.source === 'free' && (
                      <Button size="sm" onClick={() => setShowActivateModal(true)}>
                        Activate License
                      </Button>
                    )}
                  </div>
                </div>
                {/* Free Tier lesson plans are a CALENDAR-MONTH allowance that
                    renews on the 1st — state it plainly. */}
                {plan.edition === 'free' && plan.generation_limit > 0 && (
                  <p className="mt-3 text-sm text-muted-foreground">
                    {plan.generations_used} of {plan.generation_limit} lesson plans used this month ·{' '}
                    {Math.max(plan.generation_limit - plan.generations_used, 0)} remaining.
                    {' '}Your allowance renews on the 1st. Upgrade to Teacher Pro for unlimited lesson plans.
                  </p>
                )}
                {/* Free Tier AI is a one-time lifetime allowance — say so plainly
                    (never "resets tomorrow"). */}
                {plan.ai_lifetime && plan.ai_credits > 0 &&
                  Math.max(plan.ai_credits - plan.ai_credits_used, 0) === 0 && (
                  <p className="mt-3 text-sm text-muted-foreground">
                    You&apos;ve used all {plan.ai_credits} free AI generations included with the Free Tier.
                  </p>
                )}
              </SurfaceCard>
            )}

            {/* 4. Primary workflow — numbered steps, obvious current step.
                Completed steps show checkmarks and stay clickable, locked steps
                are visibly disabled. Stage completion reflects persisted
                operations (or the status fallback), never page visits. */}
            {activeScheme && (
              <SurfaceCard
                data-workflow
                accent="bg-gradient-to-r from-[#102A43] to-[#04A9CE]"
                className="px-5 py-5 sm:px-6"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="min-w-0">
                    <h2 className="text-base font-semibold text-[#102A43]">Your workflow</h2>
                    <p className="truncate text-sm text-muted-foreground">{activeScheme.filename}</p>
                  </div>
                  {activeStep >= 0 && (
                    <p className="text-sm text-muted-foreground">
                      Current step:{' '}
                      <span className="font-semibold text-[#102A43]">
                        {WORKFLOW_STEPS[activeStep].label}
                      </span>
                    </p>
                  )}
                </div>
                <div className="mt-4 overflow-x-auto pb-1">
                  <ol className="flex min-w-[520px] items-start" aria-label="Scheme workflow">
                    {WORKFLOW_STEPS.map((step, i) => {
                      // Prefer server-persisted stage state; fall back to status derivation.
                      const persisted = workflowStages?.[i]?.state
                      const done = persisted ? persisted === 'completed' : i < activeStep
                      const current = persisted ? persisted === 'active' : i === activeStep
                      const state = done ? 'done' : current ? 'current' : 'locked'
                      const stepHref =
                        i === 0 ? '/upload'
                        : i === 1 ? `/review/${activeScheme.id}`
                        : i === 2 || i === 3 ? `/generate/${activeScheme.id}`
                        : '/lessons'
                      const enabled = state !== 'locked'
                      const body = (
                        <div className={`flex flex-col items-center ${enabled ? 'cursor-pointer' : 'opacity-60'}`}>
                          <div
                            className={`flex h-9 w-9 items-center justify-center rounded-full border-2 text-sm font-bold ${
                              state === 'done'
                                ? 'border-green-500 bg-green-50 text-green-700'
                                : state === 'current'
                                  ? 'border-[#04A9CE] bg-[#102A43] text-white shadow-[0_0_0_4px_rgba(4,169,206,0.18)]'
                                  : 'border-slate-200 bg-white text-slate-400'
                            }`}
                          >
                            {state === 'done' ? '\u2713' : i + 1}
                          </div>
                          <span
                            className={`mt-1.5 block text-center text-xs leading-tight ${
                              state === 'current'
                                ? 'font-semibold text-[#102A43]'
                                : state === 'done'
                                  ? 'text-slate-600'
                                  : 'text-slate-400'
                            }`}
                          >
                            {step.label}
                          </span>
                        </div>
                      )
                      return (
                        <li key={i} className="flex flex-1 items-start">
                          {i > 0 && (
                            <div
                              aria-hidden="true"
                              className={`mt-4 h-0.5 min-w-[16px] flex-1 ${
                                done ? 'bg-green-400' : 'bg-slate-200'
                              }`}
                            />
                          )}
                          {enabled ? (
                            <Link
                              href={stepHref}
                              aria-label={step.label}
                              aria-current={state === 'current' ? 'step' : undefined}
                            >
                              {body}
                            </Link>
                          ) : (
                            body
                          )}
                        </li>
                      )
                    })}
                  </ol>
                </div>
              </SurfaceCard>
            )}

            {/* 4b. First-use empty state. */}
            {!activeScheme && (
              <SurfaceCard data-empty className="px-6 py-12 text-center">
                <FileText className="mx-auto h-12 w-12 text-slate-300" aria-hidden="true" />
                <h2 className="mt-4 text-lg font-semibold text-[#102A43]">
                  No scheme uploaded yet.
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Upload your scheme of learning to begin.
                </p>
                <div className="mt-5">
                  <Button asChild>
                    <Link href="/upload">Upload Scheme</Link>
                  </Button>
                </div>
              </SurfaceCard>
            )}

            {/* 5. Recent work — schemes table with status and next action. */}
            {schemes.length > 0 && (
              <section aria-labelledby="recent-heading" data-recent className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 id="recent-heading" className="text-lg font-semibold text-[#102A43]">
                    Recent work
                  </h2>
                  <Button variant="outline" size="sm" asChild>
                    <Link href="/upload">Upload scheme</Link>
                  </Button>
                </div>
                <SurfaceCard className="overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Scheme</TableHead>
                        <TableHead>Subject</TableHead>
                        <TableHead>Class · Term</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {schemes.map((scheme) => {
                        const nextAction = getNextAction(scheme)
                        return (
                          <TableRow key={scheme.id}>
                            <TableCell className="max-w-[240px]">
                              <span className="flex items-center gap-2">
                                <FileText className="h-4 w-4 shrink-0 text-[#04769B]" aria-hidden="true" />
                                <span className="truncate font-medium">{scheme.filename}</span>
                              </span>
                            </TableCell>
                            <TableCell>{scheme.subject}</TableCell>
                            <TableCell>
                              {scheme.class_level} · {scheme.term}
                            </TableCell>
                            <TableCell>
                              <StatusFromKey status={scheme.status} />
                            </TableCell>
                            <TableCell className="text-right">
                              <span className="flex items-center justify-end gap-2">
                                {nextAction && (
                                  <Button size="sm" variant="outline" asChild>
                                    <Link href={nextAction.href}>
                                      {nextAction.icon}
                                      {nextAction.label}
                                    </Link>
                                  </Button>
                                )}
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  aria-label="Delete scheme"
                                  onClick={() => setPendingDeleteId(scheme.id)}
                                  className="text-muted-foreground hover:text-destructive"
                                >
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </span>
                            </TableCell>
                          </TableRow>
                        )
                      })}
                    </TableBody>
                  </Table>
                </SurfaceCard>
              </section>
            )}

            {/* 6. Secondary destinations — quiet links, not another card wall. */}
            <nav
              aria-label="More destinations"
              className="flex flex-wrap gap-x-6 gap-y-2 border-t border-slate-200 pt-4 text-sm"
            >
              <Link href="/lessons" className="font-medium text-slate-600 transition-colors hover:text-[#04769B]">
                Lesson Plans
              </Link>
              <Link href="/templates" className="font-medium text-slate-600 transition-colors hover:text-[#04769B]">
                Templates
              </Link>
              <Link href="/payments" className="font-medium text-slate-600 transition-colors hover:text-[#04769B]">
                Payments
              </Link>
              <Link href="/settings" className="font-medium text-slate-600 transition-colors hover:text-[#04769B]">
                Settings
              </Link>
            </nav>
          </div>
        )}

        <Dialog open={showActivateModal} onOpenChange={setShowActivateModal}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Activate License</DialogTitle>
              <DialogDescription>
                Enter your activation code to unlock Teacher Pro features.
              </DialogDescription>
            </DialogHeader>
            {error && (
              <p className="text-sm text-destructive bg-destructive/10 p-2 rounded">{error}</p>
            )}
            <Field label="License / Activation Code" htmlFor="activation-code">
              <Input
                id="activation-code"
                type="text"
                value={activationCode}
                onChange={(e) => setActivationCode(e.target.value)}
                placeholder="Enter your activation code"
                autoFocus
              />
            </Field>
            <div className="flex gap-2">
              <Button
                onClick={handleActivateLicense}
                disabled={activating || !activationCode.trim()}
                className="flex-1"
              >
                {activating ? 'Activating…' : 'Activate License'}
              </Button>
              <Button
                variant="outline"
                onClick={() => { setShowActivateModal(false); setActivationCode(''); setError(null); }}
                disabled={activating}
              >
                Cancel
              </Button>
            </div>
          </DialogContent>
        </Dialog>

        <ConfirmDialog
          open={pendingDeleteId !== null}
          onOpenChange={(open) => {
            if (!open) setPendingDeleteId(null)
          }}
          title="Delete scheme"
          message="Are you sure you want to delete this scheme? This cannot be undone."
          confirmLabel="Delete"
          destructive
          onConfirm={() => {
            if (pendingDeleteId !== null) handleDelete(pendingDeleteId)
          }}
        />
      </main>
    </div>
  )
}
