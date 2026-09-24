'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Field } from '@/components/ui/field'
import { StatusFromKey, StatusPill } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/ui/dialog'
import { FileText, ArrowRight, Play, Eye, BookOpen, Trash2, Crown, Zap, School } from 'lucide-react'
import { api } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { PageHeader } from '@/components/ui/page-header'
import { SchemeOfWork, PlanResolution } from '@/types'

const WORKFLOW_STEPS = [
  { label: 'Upload Scheme', status: ['uploaded'] },
  { label: 'Review Curriculum', status: ['extracted'] },
  { label: 'Approve & Configure', status: ['approved'] },
  { label: 'Generate Plans', status: ['generating'] },
  { label: 'Review & Export', status: ['generated', 'completed'] },
]

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
  const pendingCount = pendingSchemes.length
  const approvedCount = approvedSchemes.length

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

  return (
    <div className="min-h-screen">
      <main className="container mx-auto px-4 py-8">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        ) : error ? (
          <Card>
            <CardContent className="p-8 text-center">
              <p className="text-destructive mb-4">{error}</p>
              <Button onClick={loadSchemes}>Try Again</Button>
            </CardContent>
          </Card>
        ) : (
          <>
            {/* First-use profile prompt (PART 18). The teacher's name is what
                the generated plan prints; when the profile has none yet we ask
                for it once here rather than falling back to a placeholder. The
                server still derives the name from the profile at generation. */}
            {user && !(user.full_name || '').trim() && (
              <Card className="mb-8 border-primary/40 bg-primary/5">
                <CardContent className="p-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                  <div>
                    <h3 className="font-semibold mb-1">Add your name to your profile</h3>
                    <p className="text-sm text-muted-foreground">
                      Your lesson plans are headed with the teacher name on your profile.
                      Add it once so every plan is labelled correctly.
                    </p>
                  </div>
                  <Button asChild>
                    <Link href="/settings">Complete Profile</Link>
                  </Button>
                </CardContent>
              </Card>
            )}

            {/* Account Card — the badge reflects the resolved entitlement
                source (§13/§14). A school teacher sees SCHOOL ACCESS and is
                NOT pushed toward buying Individual Pro; an individual teacher
                sees FREE TEACHER / TEACHER PRO with an upgrade path. */}
            {plan && (
              <Card className="mb-8">
                <CardContent className="p-6">
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                  <div className="flex items-center gap-4">
                    <div className={`p-3 rounded-full ${
                      plan.source === 'school' || plan.source === 'individual+school'
                        ? 'bg-emerald-100 text-emerald-600'
                        : plan.edition === 'teacher'
                          ? 'bg-blue-100 text-blue-600'
                          : 'bg-gray-100 text-gray-600'
                    }`}>
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
                  <div className="flex items-center gap-6 text-sm text-muted-foreground">
                    <div className="text-center">
                      <div className="font-semibold text-foreground">
                        {plan.generation_limit === 0
                          ? 'Unlimited'
                          : `${plan.generations_used}/${plan.generation_limit}`}
                      </div>
                      <div>
                        {plan.edition === 'free' ? 'Lesson plans this month' : 'Generations'}
                      </div>
                    </div>
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
                      <Button
                        size="sm"
                        className="bg-emerald-600 hover:bg-emerald-700"
                        onClick={() => setShowActivateModal(true)}
                      >
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
                </CardContent>
              </Card>
            )}

            {/* Welcome */}
            <div className="mb-8">
              <PageHeader
                title={`Welcome back, ${user.full_name?.split(' ')[0] || 'Teacher'}`}
                description={
                  schemes.length === 0
                    ? 'Get started by uploading your first scheme of work.'
                    : `You have ${schemes.length} scheme${schemes.length !== 1 ? 's' : ''} in your workspace.`
                }
              />
            </div>

            {/* Workflow - server-persisted stage state for the active scheme.
                Completed steps show checkmarks and stay clickable, the active
                step is highlighted, locked steps are visibly disabled. Stage
                completion reflects persisted operations, never page visits. */}
            {activeScheme && (
              <Card className="mb-8">
                <CardHeader className="pb-3">
                  <CardTitle className="text-lg">Your Workflow</CardTitle>
                  <CardDescription className="truncate">{activeScheme.filename}</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between text-sm overflow-x-auto">
                    {WORKFLOW_STEPS.map((step, i) => {
                      // Prefer server-persisted stage state; fall back to status derivation.
                      const persisted = workflowStages?.[i]?.state
                      const done = persisted ? persisted === 'completed' : i < activeStep
                      const current = persisted ? persisted === 'active' : i === activeStep
                      const stepHref =
                        i === 0 ? '/upload'
                        : i === 1 || i === 2 ? `/review/${activeScheme.id}`
                        : i === 3 ? `/generate/${activeScheme.id}`
                        : '/lessons'
                      const enabled = done || current
                      const body = (
                        <div className={`flex flex-col items-center ${enabled ? 'cursor-pointer' : 'opacity-50 cursor-not-allowed'}`}>
                          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${
                            done ? 'bg-green-100 text-green-700'
                            : current ? 'bg-primary text-primary-foreground'
                            : 'bg-muted text-muted-foreground'
                          }`}>
                            {done ? '\u2713' : i + 1}
                          </div>
                          <span className={`mt-1 text-xs text-center max-w-[80px] ${current ? 'font-semibold' : ''}`}>{step.label}</span>
                        </div>
                      )
                      return (
                        <div key={i} className="flex items-center">
                          {enabled ? <Link href={stepHref} aria-label={step.label}>{body}</Link> : body}
                          {i < WORKFLOW_STEPS.length - 1 && (
                            <ArrowRight className={`h-4 w-4 mx-1 mt-[-20px] ${done ? 'text-green-500' : 'text-muted-foreground'}`} />
                          )}
                        </div>
                      )
                    })}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Quick Actions. The Upload action lives in the workflow strip when a
                scheme exists, so it is only shown here for first-time users to
                avoid rendering the same button twice on one page. */}
            <div className="mb-8">
              <div className="grid md:grid-cols-4 gap-4">
                {!activeScheme && (
                  <Link href="/upload">
                    <Card className="hover:shadow-md transition-shadow cursor-pointer">
                      <CardHeader className="pb-2">
                        <FileText className="h-6 w-6 text-primary mb-2" />
                        <CardTitle className="text-base">Upload Scheme</CardTitle>
                      </CardHeader>
                    </Card>
                  </Link>
                )}
                <Link href="/lessons">
                  <Card className="hover:shadow-md transition-shadow cursor-pointer">
                    <CardHeader className="pb-2">
                      <BookOpen className="h-6 w-6 text-primary mb-2" />
                      <CardTitle className="text-base">Lesson Plans</CardTitle>
                    </CardHeader>
                  </Card>
                </Link>
                <Link href="/templates">
                  <Card className="hover:shadow-md transition-shadow cursor-pointer">
                    <CardHeader className="pb-2">
                      <Play className="h-6 w-6 text-primary mb-2" />
                      <CardTitle className="text-base">Templates</CardTitle>
                    </CardHeader>
                  </Card>
                </Link>
                {activeScheme && (getWorkflowStep(activeScheme.status) === 1 || getWorkflowStep(activeScheme.status) === 2) ? (
                  <Link href={`/review/${activeScheme.id}`}>
                    <Card className="hover:shadow-md transition-shadow cursor-pointer border-orange-300 bg-orange-50">
                      <CardHeader className="pb-2">
                        <Eye className="h-6 w-6 text-orange-600 mb-2" />
                        <CardTitle className="text-base">Continue Current Work</CardTitle>
                      </CardHeader>
                    </Card>
                  </Link>
                ) : activeScheme ? (
                  <Link href={`/generate/${activeScheme.id}`}>
                    <Card className="hover:shadow-md transition-shadow cursor-pointer border-green-300 bg-green-50">
                      <CardHeader className="pb-2">
                        <Eye className="h-6 w-6 text-green-600 mb-2" />
                        <CardTitle className="text-base">Continue Current Work</CardTitle>
                      </CardHeader>
                    </Card>
                  </Link>
                ) : (
                  <Card className="opacity-60">
                    <CardHeader className="pb-2">
                      <Eye className="h-6 w-6 text-muted-foreground mb-2" />
                      <CardTitle className="text-base">Continue Current Work</CardTitle>
                    </CardHeader>
                  </Card>
                )}
              </div>
            </div>

            {/* Workflow Summary - contextual, not navigation */}
            <div className="grid md:grid-cols-3 gap-4 mb-8">
              {pendingCount > 0 ? (
                <Link href={`/review/${pendingSchemes[0].id}`}>
                  <Card className="hover:shadow-md transition-shadow cursor-pointer border-orange-300 bg-orange-50">
                    <CardContent className="p-4">
                      <p className="text-sm text-muted-foreground">Pending Review</p>
                      <p className="text-2xl font-bold text-orange-600">{pendingCount}</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        {pendingCount === 1 ? 'Click to review' : `Click to review ${pendingSchemes[0].filename}`}
                      </p>
                    </CardContent>
                  </Card>
                </Link>
              ) : (
                <Card className="opacity-60">
                  <CardContent className="p-4">
                    <p className="text-sm text-muted-foreground">Pending Review</p>
                    <p className="text-2xl font-bold text-orange-600">0</p>
                  </CardContent>
                </Card>
              )}
              {approvedCount > 0 ? (
                <Link href={`/generate/${approvedSchemes[0].id}`}>
                  <Card className="hover:shadow-md transition-shadow cursor-pointer border-green-300 bg-green-50">
                    <CardContent className="p-4">
                      <p className="text-sm text-muted-foreground">Ready to Generate</p>
                      <p className="text-2xl font-bold text-green-600">{approvedCount}</p>
                      <p className="text-xs text-muted-foreground mt-1">Click to generate</p>
                    </CardContent>
                  </Card>
                </Link>
              ) : (
                <Card className="opacity-60">
                  <CardContent className="p-4">
                    <p className="text-sm text-muted-foreground">Ready to Generate</p>
                    <p className="text-2xl font-bold text-green-600">0</p>
                  </CardContent>
                </Card>
              )}
            </div>

            {/* Schemes List */}
            <div>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold">Your Schemes</h3>
              </div>

              {schemes.length === 0 ? (
                <Card>
                  <CardContent className="p-12 text-center">
                    <FileText className="h-16 w-16 text-muted-foreground mx-auto mb-4" />
                    <p className="text-lg font-medium mb-2">No schemes uploaded yet</p>
                    <p className="text-muted-foreground">
                      Upload your scheme of work to start generating lesson plans.
                    </p>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-3">
                  {schemes.map((scheme) => {
                    const nextAction = getNextAction(scheme)
                    return (
                      <Card key={scheme.id} className="hover:shadow-sm transition-shadow">
                        <CardContent className="p-4">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center space-x-4 min-w-0">
                              <FileText className="h-8 w-8 text-primary flex-shrink-0" />
                              <div className="min-w-0">
                                <h4 className="font-semibold truncate">{scheme.filename}</h4>
                                <p className="text-sm text-muted-foreground">
                                  {scheme.subject} &bull; {scheme.class_level} &bull; {scheme.term}
                                </p>
                              </div>
                            </div>
                            <div className="flex items-center space-x-3 flex-shrink-0">
                              <StatusFromKey status={scheme.status} className="rounded-full px-3 py-1" />
                              {nextAction && (
                                <Link href={nextAction.href}>
                                  <Button size="sm">
                                    {nextAction.icon}
                                    {nextAction.label}
                                  </Button>
                                </Link>
                              )}
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => setPendingDeleteId(scheme.id)}
                                className="text-muted-foreground hover:text-destructive"
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    )
                  })}
                </div>
              )}
            </div>
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
          </>
        )}
      </main>
    </div>
  )
}
