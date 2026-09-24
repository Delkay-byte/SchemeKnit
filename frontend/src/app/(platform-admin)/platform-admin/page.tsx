'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Field } from '@/components/ui/field'
import { Banner } from '@/components/ui/banner'
import { StatusPill } from '@/components/ui/badge'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  ConfirmDialog,
} from '@/components/ui/dialog'
import { Building2, Key, Shield, Clock, AlertTriangle, Copy, Check, RefreshCw, Eye, KeyRound } from 'lucide-react'
import { api } from '@/lib/api'
import { DEV_TOOLS_ENABLED } from '@/lib/dev-tools'
import { useAuth } from '@/lib/auth-context'
import { PageHeader } from '@/components/ui/page-header'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { formatCurrency, formatActivationDate } from '@/lib/utils-display'
import { ChangePasswordCard } from '@/components/change-password'

type Tab = 'dashboard' | 'schools' | 'licenses' | 'plans' | 'payments' | 'activations' | 'audit' | 'accounts' | 'settings'

export default function PlatformAdminPage() {
  const router = useRouter()
  const { user, loading: authLoading } = useAuth()
  const [activeTab, setActiveTab] = useState<Tab>('dashboard')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Dashboard data
  const [dashboard, setDashboard] = useState<any>(null)

  // Schools data
  const [schools, setSchools] = useState<any[]>([])
  const [showCreateSchool, setShowCreateSchool] = useState(false)
  const [newSchool, setNewSchool] = useState({ name: '', school_code: '', contact_name: '', contact_phone: '', contact_email: '', address: '' })

  // Licenses data
  const [licenses, setLicenses] = useState<any[]>([])
  const [showCreateLicense, setShowCreateLicense] = useState(false)
  const [newLicense, setNewLicense] = useState({ license_type: 'school' as 'school' | 'individual', school_id: '', teacher_email: '', product_plan_id: '', seat_limit: 10 })

  // Plans data
  const [plans, setPlans] = useState<any[]>([])
  const [showCreatePlan, setShowCreatePlan] = useState(false)
  const [newPlan, setNewPlan] = useState({ name: '', description: '', product_type: 'school', price: 0, duration_days: 365, seat_limit: 10, features: [] as string[] })

  // Payments data
  const [payments, setPayments] = useState<any[]>([])

  // Activations data
  const [activations, setActivations] = useState<any[]>([])

  // Audit data
  const [auditLogs, setAuditLogs] = useState<any[]>([])

  // Accounts data (platform-wide user list for password reset)
  const [accounts, setAccounts] = useState<any[]>([])

  // Password-reset token result modal
  const [pwResetResult, setPwResetResult] = useState<{
    token: string
    email: string
    minutes: number
  } | null>(null)
  const [resetLoadingId, setResetLoadingId] = useState<string | null>(null)
  const [copiedToken, setCopiedToken] = useState(false)

  // School drill-down
  const [schoolDetail, setSchoolDetail] = useState<any>(null)

  // Shared confirmation state — replaces window.confirm() with the shared
  // ConfirmDialog while keeping the exact confirm-then-run semantics.
  const [pendingConfirm, setPendingConfirm] = useState<{
    message: string
    title?: string
    confirmLabel?: string
    destructive?: boolean
    onConfirm: () => void
  } | null>(null)

  // Activation codes per license
  const [licenseCodes, setLicenseCodes] = useState<Record<string, any[]>>({})
  const [copiedCode, setCopiedCode] = useState<string | null>(null)

  // Demo reset — development/acceptance tooling only. The whole control is
  // compiled out of production builds (see lib/dev-tools.ts) and the backend
  // route additionally returns 403 when DEBUG is off.
  const [resetLoading, setResetLoading] = useState(false)
  const [resetResult, setResetResult] = useState<string | null>(null)

  // Maintenance mode
  const [maintenanceMode, setMaintenanceMode] = useState(false)
  const [maintenanceMessage, setMaintenanceMessage] = useState('')
  const [maintenanceRestore, setMaintenanceRestore] = useState('')

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSchoolDetail(null)
        setShowCreateSchool(false)
        setShowCreateLicense(false)
        setShowCreatePlan(false)
      }
    }
    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [])

  useEffect(() => {
    if (!authLoading && !user) {
      router.push('/login')
      return
    }
    if (!authLoading && user && user.role !== 'platform_admin') {
      router.push('/dashboard')
      return
    }
    if (user) {
      loadTabData(activeTab)
    }
  }, [user, authLoading, activeTab])

  const loadTabData = async (tab: Tab) => {
    try {
      setLoading(true)
      setError(null)
      switch (tab) {
        case 'dashboard':
          const dash = await api.getPlatformDashboard()
          setDashboard(dash)
          break
        case 'schools':
          const sch = await api.listSchools()
          setSchools(sch.schools || [])
          break
        case 'licenses':
          const lic = await api.listLicenses()
          setLicenses(lic.licenses || [])
          const pl = await api.listPlatformPlans()
          setPlans(pl.plans || [])
          const sch2 = await api.listSchools()
          setSchools(sch2.schools || [])
          break
        case 'plans':
          const pl2 = await api.listPlatformPlans()
          setPlans(pl2.plans || [])
          break
        case 'payments':
          const pay = await api.listPlatformPayments()
          setPayments(pay.payments || [])
          break
        case 'activations':
          const [act, indAct] = await Promise.all([
            api.listActivationCodes().catch(() => ({ activations: [] })),
            api.listIndividualActivationCodes().catch(() => ({ codes: [] })),
          ])
          const allActivations = [
            ...(act.activations || []).map((a: any) => ({ ...a, type: 'school' })),
            ...(indAct.codes || []).map((c: any) => ({ ...c, type: 'individual' })),
          ]
          setActivations(allActivations)
          break
        case 'audit':
          const aud = await api.listPlatformAuditLogs(50)
          setAuditLogs(aud.logs || [])
          break
        case 'accounts':
          const usr = await api.listUsers()
          setAccounts(usr.users || [])
          break
        case 'settings':
          break
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }

  const handleCreateSchool = async () => {
    if (!newSchool.name.trim() || !newSchool.school_code.trim()) {
      setError('School name and code are required')
      return
    }
    try {
      await api.createSchool(newSchool)
      setShowCreateSchool(false)
      setNewSchool({ name: '', school_code: '', contact_name: '', contact_phone: '', contact_email: '', address: '' })
      loadTabData('schools')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create school')
    }
  }

  const handleCreateLicense = async () => {
    if (newLicense.license_type === 'individual') {
      if (!newLicense.teacher_email || !newLicense.product_plan_id) {
        setError('Please enter teacher email and select a plan')
        return
      }
      try {
        await api.createIndividualActivationCode(newLicense.teacher_email, newLicense.product_plan_id)
        setShowCreateLicense(false)
        setNewLicense({ license_type: 'school', school_id: '', teacher_email: '', product_plan_id: '', seat_limit: 10 })
        loadTabData('activations')
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to create individual activation')
      }
    } else {
      if (!newLicense.school_id || !newLicense.product_plan_id) {
        setError('Please select a school and a plan')
        return
      }
      try {
        await api.createLicense({ school_id: newLicense.school_id, product_plan_id: newLicense.product_plan_id, seat_limit: newLicense.seat_limit })
        setShowCreateLicense(false)
        setNewLicense({ license_type: 'school', school_id: '', teacher_email: '', product_plan_id: '', seat_limit: 10 })
        loadTabData('licenses')
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to create license')
      }
    }
  }

  const handleCreatePlan = async () => {
    if (!newPlan.name.trim()) {
      setError('Plan name is required')
      return
    }
    try {
      await api.createPlatformPlan(newPlan)
      setShowCreatePlan(false)
      setNewPlan({ name: '', description: '', product_type: 'school', price: 0, duration_days: 365, seat_limit: 10, features: [] })
      loadTabData('plans')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create plan')
    }
  }

  const viewSchool = async (schoolId: string) => {
    try {
      setError(null)
      const detail = await api.getSchool(schoolId)
      setSchoolDetail(detail)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load school')
    }
  }

  const toggleLicenseCodes = async (licenseId: string) => {
    try {
      setError(null)
      if (licenseCodes[licenseId]) {
        setLicenseCodes((prev) => {
          const next = { ...prev }
          delete next[licenseId]
          return next
        })
        return
      }
      const res = await api.listLicenseActivationCodes(licenseId)
      setLicenseCodes((prev) => ({ ...prev, [licenseId]: res.activation_codes || [] }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load activation codes')
    }
  }

  const handleGenerateCode = async (licenseId: string) => {
    try {
      setError(null)
      await api.generateActivationCode(licenseId)
      const res = await api.listLicenseActivationCodes(licenseId)
      setLicenseCodes((prev) => ({ ...prev, [licenseId]: res.activation_codes || [] }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to generate activation code')
    }
  }

  const copyCode = async (code: string) => {
    try {
      await navigator.clipboard.writeText(code)
    } catch {
      const ta = document.createElement('textarea')
      ta.value = code
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    setCopiedCode(code)
    setTimeout(() => setCopiedCode(null), 2000)
  }

  const handleInitiateReset = async (userId: string, name: string, email: string) => {
    try {
      setResetLoadingId(userId)
      setError(null)
      const res = await api.initiatePasswordReset(userId)
      setPwResetResult({
        token: res.reset_token,
        email: res.target_email,
        minutes: res.expires_in_minutes,
      })
      // Refresh accounts if on that tab
      if (activeTab === 'accounts') {
        const usr = await api.listUsers()
        setAccounts(usr.users || [])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to initiate reset')
    } finally {
      setResetLoadingId(null)
    }
  }

  const copyToken = async () => {
    if (!pwResetResult) return
    try {
      await navigator.clipboard.writeText(pwResetResult.token)
    } catch {
      const ta = document.createElement('textarea')
      ta.value = pwResetResult.token
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    setCopiedToken(true)
    setTimeout(() => setCopiedToken(false), 2000)
  }

  // Development/acceptance tooling. Never rendered in production builds
  // (DEV_TOOLS_ENABLED folds to false and is tree-shaken out), and the backend
  // refuses the call with 403 unless DEBUG is on.
  const handleResetDemo = async () => {
    if (!DEV_TOOLS_ENABLED) return
    setResetLoading(true)
    setResetResult(null)
    try {
      const res = await api.resetDemoData()
      setResetResult('Demo commercial data reset. ' + JSON.stringify(res.removed || {}))
      setSchoolDetail(null)
      setLicenseCodes({})
      loadTabData(activeTab)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reset demo data')
    } finally {
      setResetLoading(false)
    }
  }

  if (authLoading || !user || user.role !== 'platform_admin') {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <main className="container mx-auto px-4 py-8 max-w-7xl">
        <PageHeader
          className="mb-6"
          eyebrow="Platform"
          title={
            <span className="flex items-center gap-2">
              <Shield className="h-6 w-6" aria-hidden="true" />
              Platform Administration
            </span>
          }
          description="BloomCore / SchemeKnit Platform Management"
        />

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as Tab)} className="mb-6">
          <TabsList
            aria-label="Console sections"
            className="h-auto max-w-full flex-wrap justify-start gap-1 bg-transparent p-0"
          >
            {(['dashboard', 'schools', 'licenses', 'plans', 'payments', 'activations', 'audit', 'accounts', 'settings'] as Tab[]).map((tab) => (
              <TabsTrigger
                key={tab}
                value={tab}
                className="capitalize border border-border bg-background px-3 py-1.5 text-muted-foreground data-[state=active]:border-[#04A9CE]/40 data-[state=active]:bg-[#04A9CE]/10 data-[state=active]:text-[#04769B]"
              >
                {tab}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        {error && <Banner tone="danger" className="mb-4">{error}</Banner>}

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        ) : (
          <>
            {/* Dashboard Tab */}
            {activeTab === 'dashboard' && dashboard && (
              <div className="space-y-6">
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  <SurfaceCard className="flex items-center justify-between px-5 py-4">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Active Schools</p>
                      <p className="mt-1.5 text-2xl font-bold text-[#102A43]">{dashboard.active_schools}</p>
                    </div>
                    <Building2 className="h-8 w-8 text-[#04A9CE]" aria-hidden="true" />
                  </SurfaceCard>
                  <SurfaceCard className="flex items-center justify-between px-5 py-4">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Active Licenses</p>
                      <p className="mt-1.5 text-2xl font-bold text-[#102A43]">{dashboard.active_licenses}</p>
                    </div>
                    <Key className="h-8 w-8 text-green-500" aria-hidden="true" />
                  </SurfaceCard>
                  <SurfaceCard className="flex items-center justify-between px-5 py-4">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Expiring Soon</p>
                      <p className="mt-1.5 text-2xl font-bold text-orange-600">{dashboard.expiring_soon}</p>
                    </div>
                    <Clock className="h-8 w-8 text-orange-500" aria-hidden="true" />
                  </SurfaceCard>
                  <SurfaceCard className="flex items-center justify-between px-5 py-4">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Expired</p>
                      <p className="mt-1.5 text-2xl font-bold text-red-600">{dashboard.expired_licenses}</p>
                    </div>
                    <AlertTriangle className="h-8 w-8 text-red-500" aria-hidden="true" />
                  </SurfaceCard>
                </div>
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  <SurfaceCard className="px-5 py-4">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Total Teachers</p>
                    <p className="mt-1.5 text-2xl font-bold text-[#102A43]">{dashboard.total_teachers}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{dashboard.seats_available} seats available</p>
                  </SurfaceCard>
                  <SurfaceCard className="px-5 py-4">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Pending Payments</p>
                    <p className="mt-1.5 text-2xl font-bold text-[#102A43]">{dashboard.pending_payments}</p>
                  </SurfaceCard>
                  <SurfaceCard className="px-5 py-4">
                    <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Verified Revenue</p>
                    <p className="mt-1.5 text-2xl font-bold text-[#102A43]">{formatCurrency(dashboard.verified_revenue)}</p>
                  </SurfaceCard>
                </div>

                {/* Development/acceptance-only demo data reset. Compiled out
                    of production builds; backend also 403s unless DEBUG is on. */}
                {DEV_TOOLS_ENABLED && (
                <SurfaceCard className="flex flex-wrap items-center justify-between gap-3 border-destructive/40 px-5 py-4">
                  <div className="min-w-0">
                    <p className="font-medium text-[#102A43]">Reset demo commercial data</p>
                    <p className="text-xs text-muted-foreground">
                      Development only. Removes demo schools, licenses, activation codes, payments and
                      teacher/school-admin accounts. Platform configuration is never deleted.
                    </p>
                    {resetResult && <p className="mt-1 text-xs text-green-600">{resetResult}</p>}
                  </div>
                  <Button variant="destructive" onClick={() => setPendingConfirm({
                    title: 'Reset demo commercial data',
                    message: 'RESET DEMO COMMERCIAL DATA\n\nDeletes demo schools, licenses, activation codes, payments and teacher/school-admin accounts. Platform configuration (platform admins, plans, payment settings) is kept.\n\nContinue?',
                    destructive: true,
                    confirmLabel: 'Reset',
                    onConfirm: handleResetDemo,
                  })} disabled={resetLoading}>
                    <RefreshCw className="h-4 w-4 mr-1.5" />
                    {resetLoading ? 'Resetting...' : 'RESET DEMO COMMERCIAL DATA'}
                  </Button>
                </SurfaceCard>
                )}
              </div>
            )}

            {/* Schools Tab */}
            {activeTab === 'schools' && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold text-[#102A43]">Schools ({schools.length})</h2>
                    <p className="text-sm text-muted-foreground">Registered schools and their license standing.</p>
                  </div>
                  <Button onClick={() => setShowCreateSchool(true)}>Create School</Button>
                </div>
                {schools.length === 0 ? (
                  <SurfaceCard className="px-6 py-10 text-center">
                    <p className="font-medium text-[#102A43]">No schools yet</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Create the first school to start issuing licenses.
                    </p>
                  </SurfaceCard>
                ) : (
                <SurfaceCard className="overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-muted/50 hover:bg-muted/50">
                        <TableHead>School</TableHead>
                        <TableHead>Code</TableHead>
                        <TableHead>Teachers</TableHead>
                        <TableHead>License</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {schools.map((s) => (
                        <TableRow key={s.id}>
                          <TableCell className="font-medium">{s.name}</TableCell>
                          <TableCell className="text-muted-foreground">{s.school_code}</TableCell>
                          <TableCell>{s.teacher_count}</TableCell>
                          <TableCell>
                            {s.has_active_license ? (
                              <span className="text-xs text-green-700">License expires: {s.license_expiry}</span>
                            ) : (
                              <span className="text-xs text-orange-600">No active license</span>
                            )}
                          </TableCell>
                          <TableCell>
                            <StatusPill tone={s.status === 'active' ? 'success' : s.status === 'suspended' ? 'danger' : 'neutral'}>
                              {s.status}
                            </StatusPill>
                          </TableCell>
                          <TableCell className="text-right">
                            <Button size="sm" variant="outline" onClick={() => viewSchool(s.id)}>
                              <Eye className="h-4 w-4 mr-1.5" />
                              View
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </SurfaceCard>
                )}
              </div>
            )}

            {/* Licenses Tab */}
            {activeTab === 'licenses' && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold text-[#102A43]">Licenses ({licenses.length})</h2>
                    <p className="text-sm text-muted-foreground">School and teacher licenses, seats and activation codes.</p>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="outline" onClick={() => loadTabData('licenses')}>
                      <RefreshCw className="h-4 w-4 mr-1.5" />
                      Refresh
                    </Button>
                    <Button onClick={() => setShowCreateLicense(true)}>Create License</Button>
                  </div>
                </div>
                {licenses.length === 0 && (
                  <SurfaceCard className="px-6 py-10 text-center">
                    <p className="font-medium text-[#102A43]">No licenses yet</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Create a license for a school or an individual teacher.
                    </p>
                  </SurfaceCard>
                )}
                {licenses.map((l) => {
                  const eff = l.effective_status || l.status
                  return (
                  <SurfaceCard key={l.id} className="px-5 py-4">
                    <div className="space-y-3">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <h3 className="font-semibold text-[#102A43]">{l.school_name}</h3>
                          <p className="text-sm text-muted-foreground">Code: {l.license_code} &bull; Plan: {l.plan_name}</p>
                          <p className="text-xs text-muted-foreground">
                            Seats: {l.seats_used}/{l.seat_limit} used
                            {typeof l.seats_available === 'number' && ` (${l.seats_available} available)`} &bull; Expires: {l.expiry_date}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {l.claimed_by_school
                              ? `Activated: ${formatActivationDate(l.activated_at)}${l.activation_code ? ` \u2022 code ${l.activation_code}` : ''}`
                              : 'Not yet claimed by a school \u2014 activation code not redeemed'}
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <StatusPill tone={eff === 'active' ? 'success' : eff === 'expired' || eff === 'cancelled' ? 'danger' : eff === 'suspended' ? 'caution' : 'warning'} className="uppercase">
                            {eff}
                          </StatusPill>
                          {eff === 'active' && (
                            <Button size="sm" variant="outline" onClick={() => setPendingConfirm({
                              title: 'Suspend license',
                              message: `Suspend license for ${l.school_name}?`,
                              onConfirm: () => api.suspendLicense(l.id).then(() => loadTabData('licenses')).catch((err) => setError(err.message || 'Failed to suspend')),
                            })}>Suspend</Button>
                          )}
                          {eff !== 'active' && eff !== 'cancelled' && (
                            <Button size="sm" variant="outline" onClick={() => setPendingConfirm({
                              title: 'Activate license',
                              message: `Activate license for ${l.school_name}?`,
                              onConfirm: () => api.activateLicense(l.id).then(() => loadTabData('licenses')).catch((err) => setError(err.message || 'Failed to activate')),
                            })}>Activate</Button>
                          )}
                          <Button size="sm" variant="outline" onClick={() => setPendingConfirm({
                            title: 'Renew license',
                            message: `Renew license for ${l.school_name}?`,
                            onConfirm: () => api.renewLicense(l.id).then(() => loadTabData('licenses')).catch((err) => setError(err.message || 'Failed to renew')),
                          })}>Renew</Button>
                          <Button size="sm" variant="outline" onClick={() => toggleLicenseCodes(l.id)}>
                            <Key className="h-4 w-4 mr-1.5" />
                            Activation Codes
                          </Button>
                        </div>
                      </div>

                      {licenseCodes[l.id] && (
                        <div className="border rounded-lg p-3 bg-muted/40">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-sm font-medium">Activation Codes</span>
                            <Button size="sm" onClick={() => handleGenerateCode(l.id)}>
                              <RefreshCw className="h-4 w-4 mr-1.5" />
                              Generate Code
                            </Button>
                          </div>
                          {licenseCodes[l.id].length === 0 ? (
                            <p className="text-sm text-muted-foreground">No codes yet &mdash; click Generate Code.</p>
                          ) : (
                            <div className="space-y-2">
                              {licenseCodes[l.id].map((c) => (
                                <div key={c.id} className="flex items-center justify-between gap-3 bg-background border rounded p-2">
                                  <span className="font-mono font-semibold">{c.code}</span>
                                  <div className="flex items-center gap-2">
                                    <StatusPill tone={c.status === 'active' ? 'success' : c.status === 'used' ? 'info' : 'danger'}>
                                      {c.status === 'used' ? 'used' : c.status === 'active' ? 'unused' : 'revoked'}
                                    </StatusPill>
                                    <Button size="sm" variant="outline" onClick={() => copyCode(c.code)}>
                                      {copiedCode === c.code ? <Check className="h-4 w-4 mr-1.5" /> : <Copy className="h-4 w-4 mr-1.5" />}
                                      {copiedCode === c.code ? 'Copied' : 'Copy'}
                                    </Button>
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </SurfaceCard>
                  )
                })}
              </div>
            )}

            {/* Plans Tab */}
            {activeTab === 'plans' && (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold text-[#102A43]">Product Plans ({plans.length})</h2>
                    <p className="text-sm text-muted-foreground">Plans available for schools and individual teachers.</p>
                  </div>
                  <Button onClick={() => setShowCreatePlan(true)}>Create Plan</Button>
                </div>
                {plans.length === 0 ? (
                  <SurfaceCard className="px-6 py-10 text-center">
                    <p className="font-medium text-[#102A43]">No product plans yet</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Create a plan before issuing licenses against it.
                    </p>
                  </SurfaceCard>
                ) : (
                <SurfaceCard className="overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-muted/50 hover:bg-muted/50">
                        <TableHead>Plan</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Seats</TableHead>
                        <TableHead>Duration</TableHead>
                        <TableHead className="text-right">Price</TableHead>
                        <TableHead className="text-right">Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {plans.map((p) => (
                        <TableRow key={p.id}>
                          <TableCell>
                            <p className="font-medium text-[#102A43]">{p.name}</p>
                            <p className="text-xs text-muted-foreground">{p.description}</p>
                          </TableCell>
                          <TableCell className="capitalize text-muted-foreground">{p.product_type}</TableCell>
                          <TableCell>{p.seat_limit}</TableCell>
                          <TableCell className="text-muted-foreground">{p.duration_days || 'Unlimited'} days</TableCell>
                          <TableCell className="text-right font-semibold">{formatCurrency(p.price)}</TableCell>
                          <TableCell className="text-right">
                            <StatusPill tone={p.active ? 'success' : 'danger'}>
                              {p.active ? 'Active' : 'Inactive'}
                            </StatusPill>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </SurfaceCard>
                )}
              </div>
            )}

            {/* Payments Tab */}
            {activeTab === 'payments' && (
              <div className="space-y-4">
                <div>
                  <h2 className="text-lg font-semibold text-[#102A43]">Payments ({payments.length})</h2>
                  <p className="text-sm text-muted-foreground">Incoming payments awaiting or holding verification.</p>
                </div>
                {payments.length === 0 ? (
                  <SurfaceCard className="px-6 py-10 text-center">
                    <p className="font-medium text-[#102A43]">No payments yet</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Payments submitted by schools and teachers will appear here.
                    </p>
                  </SurfaceCard>
                ) : (
                <SurfaceCard className="overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-muted/50 hover:bg-muted/50">
                        <TableHead>Payer</TableHead>
                        <TableHead className="text-right">Amount</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {payments.map((p) => (
                        <TableRow key={p.id}>
                          <TableCell>
                            <p className="font-medium text-[#102A43]">{p.payer_name}</p>
                            <p className="text-xs text-muted-foreground">
                              {p.payment_method} &bull; {p.product_name}
                            </p>
                          </TableCell>
                          <TableCell className="text-right font-semibold">{formatCurrency(p.amount)}</TableCell>
                          <TableCell>
                            <StatusPill tone={p.status === 'verified' ? 'success' : p.status === 'rejected' ? 'danger' : 'warning'}>
                              {p.status}
                            </StatusPill>
                          </TableCell>
                          <TableCell className="text-right">
                            {p.status === 'pending' && (
                              <div className="flex justify-end gap-2">
                                <Button size="sm" onClick={() => setPendingConfirm({
                                  title: 'Verify payment',
                                  message: `Verify ${p.payment_method} payment of ${formatCurrency(p.amount)} from ${p.payer_name}?`,
                                  onConfirm: () => api.platformVerifyPayment(p.id).then(() => loadTabData('payments')).catch((err) => setError(err.message || 'Failed to verify')),
                                })}>Verify</Button>
                                <Button size="sm" variant="destructive" onClick={() => setPendingConfirm({
                                  title: 'Reject payment',
                                  message: `Reject payment from ${p.payer_name}?`,
                                  destructive: true,
                                  confirmLabel: 'Reject',
                                  onConfirm: () => api.platformRejectPayment(p.id, 'Rejected by admin').then(() => loadTabData('payments')).catch((err) => setError(err.message || 'Failed to reject')),
                                })}>Reject</Button>
                              </div>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </SurfaceCard>
                )}
              </div>
            )}

            {/* Activations Tab */}
            {activeTab === 'activations' && (
              <div className="space-y-4">
                <div>
                  <h2 className="text-lg font-semibold text-[#102A43]">Activation Codes ({activations.length})</h2>
                  <p className="text-sm text-muted-foreground">School and individual activation codes.</p>
                </div>
                {activations.length === 0 ? (
                  <SurfaceCard className="px-6 py-10 text-center">
                    <p className="font-medium text-[#102A43]">No activation codes yet</p>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Codes generated from a license will appear here.
                    </p>
                  </SurfaceCard>
                ) : (
                <SurfaceCard className="overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-muted/50 hover:bg-muted/50">
                        <TableHead>Code</TableHead>
                        <TableHead>Type</TableHead>
                        <TableHead>Issued to</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {activations.map((a) => (
                        <TableRow key={a.id}>
                          <TableCell className="font-mono font-semibold">{a.code}</TableCell>
                          <TableCell>
                            <StatusPill tone={a.type === 'individual' ? 'accent' : 'info'}>
                              {a.type === 'individual' ? 'Individual' : 'School'}
                            </StatusPill>
                          </TableCell>
                          <TableCell className="text-muted-foreground">
                            {a.type === 'individual' ? (a.teacher_email || 'Individual teacher') : (a.license_code || 'N/A')}
                            &bull; {a.used_by_school || a.used_by_user_id || 'Not used'}
                          </TableCell>
                          <TableCell>
                            <StatusPill tone={a.status === 'active' ? 'success' : a.status === 'used' ? 'info' : 'danger'}>
                              {a.status}
                            </StatusPill>
                          </TableCell>
                          <TableCell className="text-right">
                            {a.status === 'active' && (
                              <Button size="sm" variant="outline" onClick={() => setPendingConfirm({
                                title: 'Revoke activation code',
                                message: `Revoke activation code ${a.code}?`,
                                destructive: true,
                                confirmLabel: 'Revoke',
                                onConfirm: () => api.revokeActivationCode(a.id).then(() => loadTabData('activations')).catch((err) => setError(err.message || 'Failed to revoke')),
                              })}>Revoke</Button>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </SurfaceCard>
                )}
              </div>
            )}

            {/* Audit Tab */}
            {activeTab === 'audit' && (
              <div className="space-y-4">
                <div>
                  <h2 className="text-lg font-semibold text-[#102A43]">Audit Log ({auditLogs.length})</h2>
                  <p className="text-sm text-muted-foreground">Most recent platform actions, newest first.</p>
                </div>
                {auditLogs.length === 0 ? (
                  <SurfaceCard className="px-6 py-10 text-center">
                    <p className="font-medium text-[#102A43]">No audit entries yet</p>
                  </SurfaceCard>
                ) : (
                <SurfaceCard className="divide-y divide-[#102A43]/8 px-5 py-1">
                  {auditLogs.map((l) => (
                    <div key={l.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
                      <div className="min-w-0">
                        <span className="font-medium text-[#102A43]">{l.action}</span>
                        <span className="ml-2 text-muted-foreground">{l.target_type} {l.target_id ? `#${l.target_id.slice(0, 8)}` : ''}</span>
                      </div>
                      <span className="text-muted-foreground">{l.timestamp ? new Date(l.timestamp).toLocaleString() : ''}</span>
                    </div>
                  ))}
                </SurfaceCard>
                )}
              </div>
            )}

            {/* Accounts Tab — platform-wide user list + password reset */}
            {activeTab === 'accounts' && (
              <div className="space-y-4">
                <div>
                  <h2 className="text-lg font-semibold text-[#102A43]">Platform Accounts ({accounts.length})</h2>
                  <p className="text-sm text-muted-foreground">
                    Initiate a one-time password reset for any account. The reset
                    token is shown once — deliver it to the user out-of-band.
                  </p>
                </div>
                {accounts.length === 0 ? (
                  <SurfaceCard className="px-6 py-10 text-center">
                    <p className="font-medium text-[#102A43]">No accounts yet</p>
                  </SurfaceCard>
                ) : (
                <SurfaceCard className="overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-muted/50 hover:bg-muted/50">
                        <TableHead>Account</TableHead>
                        <TableHead className="text-right">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {accounts.map((u) => (
                        <TableRow key={u.id}>
                          <TableCell>
                            <span className="font-medium text-[#102A43]">{u.full_name}</span>
                            <span className="ml-2 text-muted-foreground">&lt;{u.email}&gt;</span>
                            <StatusPill tone="neutral" className="ml-2">
                              {u.role}
                            </StatusPill>
                            {!u.is_active && (
                              <StatusPill tone="danger" className="ml-2">
                                disabled
                              </StatusPill>
                            )}
                          </TableCell>
                          <TableCell className="text-right">
                            {u.id !== user?.id && (
                              <Button
                                variant="outline"
                                size="sm"
                                disabled={resetLoadingId === u.id || !u.is_active}
                                onClick={() => setPendingConfirm({
                                  title: 'Initiate password reset',
                                  message: `You are about to initiate a password reset for ${u.full_name} (${u.email}).\n\nA one-time reset token will be generated. Continue?`,
                                  onConfirm: () => handleInitiateReset(u.id, u.full_name, u.email),
                                })}
                              >
                                {resetLoadingId === u.id ? (
                                  'Working...'
                                ) : (
                                  <>
                                    <KeyRound className="h-4 w-4 mr-1" />
                                    Initiate Password Reset
                                  </>
                                )}
                              </Button>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </SurfaceCard>
                )}
              </div>
            )}

            {/* Settings Tab */}
            {activeTab === 'settings' && (
              <div className="space-y-6 max-w-2xl">
                <div>
                  <h2 className="text-lg font-semibold text-[#102A43]">Platform Settings</h2>
                  <p className="text-sm text-muted-foreground">Your admin credentials and site-wide maintenance.</p>
                </div>
                <ChangePasswordCard />
                <MaintenanceControl />
              </div>
            )}
          </>
        )}

        {/* School Detail Modal */}
        {schoolDetail && (
          <Dialog open onOpenChange={(open) => { if (!open) setSchoolDetail(null) }}>
            <DialogContent className="max-w-2xl">
              <DialogHeader>
                <DialogTitle>{schoolDetail.name}</DialogTitle>
                <DialogDescription>
                  Code: {schoolDetail.school_code} &bull; Status: {schoolDetail.status}
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-6">
                <div className="grid md:grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="font-medium mb-1">Contact</p>
                    <p className="text-muted-foreground">{schoolDetail.contact_name || '\u2014'}</p>
                    <p className="text-muted-foreground">{schoolDetail.contact_phone || '\u2014'}</p>
                    <p className="text-muted-foreground">{schoolDetail.contact_email || '\u2014'}</p>
                  </div>
                  <div>
                    <p className="font-medium mb-1">Licence</p>
                    {schoolDetail.license ? (
                      <>
                        <p className="text-muted-foreground">License: {schoolDetail.license.license_code}</p>
                        <p className="text-muted-foreground">
                          Status: <span className="uppercase">{schoolDetail.license.effective_status || schoolDetail.license.status}</span>
                        </p>
                        <p className="text-muted-foreground">
                          {schoolDetail.license.claimed_by_school
                            ? `Activated: ${formatActivationDate(schoolDetail.license.activated_at)}`
                            : 'Not yet claimed by a school'}
                        </p>
                        <p className="text-muted-foreground">Expiry: {schoolDetail.license.expiry_date}</p>
                        <p className="text-muted-foreground">
                          Seats: {schoolDetail.license.seats_used}/{schoolDetail.license.seat_limit} used
                        </p>
                      </>
                    ) : (
                      <p className="text-orange-600">No active licence</p>
                    )}
                  </div>
                </div>

                <div>
                  <p className="font-medium mb-2">
                    Teachers &amp; Administrators ({schoolDetail.teachers?.length || 0})
                  </p>
                  {schoolDetail.teachers?.length ? (
                    <div className="space-y-1">
                      {schoolDetail.teachers.map((t: any) => (
                        <div key={t.id} className="flex items-center justify-between text-sm border rounded p-2 flex-wrap gap-2">
                          <span>{t.full_name} &lt;{t.email}&gt;</span>
                          <span className="flex items-center gap-2">
                            <span className="text-muted-foreground">{t.role}</span>
                            <StatusPill tone={t.is_active ? 'success' : 'danger'}>
                              {t.is_active ? 'active' : 'inactive'}
                            </StatusPill>
                            {t.id !== user?.id && t.is_active && (
                              <Button
                                variant="ghost"
                                size="sm"
                                disabled={resetLoadingId === t.id}
                                onClick={() => setPendingConfirm({
                                  title: 'Initiate password reset',
                                  message: `You are about to initiate a password reset for ${t.full_name} (${t.email}).\n\nA one-time reset token will be generated. Continue?`,
                                  onConfirm: () => handleInitiateReset(t.id, t.full_name, t.email),
                                })}
                                title="Initiate password reset"
                              >
                                {resetLoadingId === t.id ? (
                                  'Working...'
                                ) : (
                                  <KeyRound className="h-4 w-4" />
                                )}
                              </Button>
                            )}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">No users yet.</p>
                  )}
                </div>

                <div className="flex justify-end">
                  <Button variant="outline" onClick={() => setSchoolDetail(null)}>Close</Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        )}

        {/* Create School Modal */}
        {showCreateSchool && (
          <Dialog open onOpenChange={setShowCreateSchool}>
            <DialogContent className="max-w-md">
              <DialogHeader>
                <DialogTitle>Create School</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <Input type="text" placeholder="School Name" value={newSchool.name} onChange={(e) => setNewSchool({ ...newSchool, name: e.target.value })} />
                <Input type="text" placeholder="School Code (e.g., AWASIVE-001)" value={newSchool.school_code} onChange={(e) => setNewSchool({ ...newSchool, school_code: e.target.value })} />
                <Input type="text" placeholder="Contact Name" value={newSchool.contact_name} onChange={(e) => setNewSchool({ ...newSchool, contact_name: e.target.value })} />
                <Input type="text" placeholder="Contact Phone" value={newSchool.contact_phone} onChange={(e) => setNewSchool({ ...newSchool, contact_phone: e.target.value })} />
                <Input type="email" placeholder="Contact Email" value={newSchool.contact_email} onChange={(e) => setNewSchool({ ...newSchool, contact_email: e.target.value })} />
                <Input type="text" placeholder="Address (optional)" value={newSchool.address} onChange={(e) => setNewSchool({ ...newSchool, address: e.target.value })} />
                <div className="flex gap-2">
                  <Button onClick={handleCreateSchool}>Create</Button>
                  <Button variant="outline" onClick={() => setShowCreateSchool(false)}>Cancel</Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        )}

        {/* Create License Modal */}
        {showCreateLicense && (
          <Dialog open onOpenChange={setShowCreateLicense}>
            <DialogContent className="max-w-md">
              <DialogHeader>
                <DialogTitle>Create License</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div className="flex gap-2">
                  <Button variant={newLicense.license_type === 'school' ? 'default' : 'outline'} onClick={() => setNewLicense({ ...newLicense, license_type: 'school', school_id: '' })}>School</Button>
                  <Button variant={newLicense.license_type === 'individual' ? 'default' : 'outline'} onClick={() => setNewLicense({ ...newLicense, license_type: 'individual', teacher_email: '' })}>Individual Teacher</Button>
                </div>
                {newLicense.license_type === 'school' ? (
                  <Select value={newLicense.school_id} onChange={(e) => setNewLicense({ ...newLicense, school_id: e.target.value })}>
                    <option value="">Select School</option>
                    {schools.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </Select>
                ) : (
                  <Input type="email" placeholder="Teacher Email" value={newLicense.teacher_email} onChange={(e) => setNewLicense({ ...newLicense, teacher_email: e.target.value })} />
                )}
                <Select value={newLicense.product_plan_id} onChange={(e) => setNewLicense({ ...newLicense, product_plan_id: e.target.value })}>
                  <option value="">Select Plan</option>
                  {plans.map((p) => <option key={p.id} value={p.id}>{p.name} ({formatCurrency(p.price)})</option>)}
                </Select>
                {newLicense.license_type === 'school' && (
                  <Input type="number" placeholder="Seat Limit" value={newLicense.seat_limit} onChange={(e) => setNewLicense({ ...newLicense, seat_limit: parseInt(e.target.value) || 10 })} />
                )}
                <div className="flex gap-2">
                  <Button onClick={handleCreateLicense}>{newLicense.license_type === 'individual' ? 'Create & Send Code' : 'Create'}</Button>
                  <Button variant="outline" onClick={() => setShowCreateLicense(false)}>Cancel</Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        )}

        {/* Create Plan Modal */}
        {showCreatePlan && (
          <Dialog open onOpenChange={setShowCreatePlan}>
            <DialogContent className="max-w-md">
              <DialogHeader>
                <DialogTitle>Create Product Plan</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <Input type="text" placeholder="Plan Name" value={newPlan.name} onChange={(e) => setNewPlan({ ...newPlan, name: e.target.value })} />
                <Input type="text" placeholder="Description" value={newPlan.description} onChange={(e) => setNewPlan({ ...newPlan, description: e.target.value })} />
                <Select value={newPlan.product_type} onChange={(e) => setNewPlan({ ...newPlan, product_type: e.target.value })}>
                  <option value="school">School</option>
                  <option value="individual">Individual</option>
                </Select>
                <Input type="number" placeholder="Price (GH₵)" value={newPlan.price} onChange={(e) => setNewPlan({ ...newPlan, price: parseFloat(e.target.value) || 0 })} />
                <Input type="number" placeholder="Duration (days)" value={newPlan.duration_days || ''} onChange={(e) => setNewPlan({ ...newPlan, duration_days: parseInt(e.target.value) || 365 })} />
                <Input type="number" placeholder="Seat Limit" value={newPlan.seat_limit} onChange={(e) => setNewPlan({ ...newPlan, seat_limit: parseInt(e.target.value) || 10 })} />
                <div className="flex gap-2">
                  <Button onClick={handleCreatePlan}>Create</Button>
                  <Button variant="outline" onClick={() => setShowCreatePlan(false)}>Cancel</Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        )}

        {/* Password Reset Token Modal */}
        {pwResetResult && (
          <Dialog open onOpenChange={(open) => { if (!open) setPwResetResult(null) }}>
            <DialogContent className="max-w-lg">
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  <KeyRound className="h-5 w-5" />
                  Password Reset Token
                </DialogTitle>
                <DialogDescription>
                  For <strong>{pwResetResult.email}</strong> — expires in {pwResetResult.minutes} minutes.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4">
                <Banner tone="warning">
                  This token is shown <strong>once</strong>. Deliver it to the
                  user out-of-band (phone, in person). The user completes the
                  reset at <strong>/reset-password</strong>.
                </Banner>
                <div className="p-3 bg-muted rounded-lg font-mono text-sm break-all">
                  {pwResetResult.token}
                </div>
                <div className="flex gap-2">
                  <Button onClick={copyToken} className="flex-1">
                    {copiedToken ? <Check className="h-4 w-4 mr-2" /> : <Copy className="h-4 w-4 mr-2" />}
                    {copiedToken ? 'Copied' : 'Copy Token'}
                  </Button>
                  <Button variant="outline" onClick={() => setPwResetResult(null)}>
                    Done
                  </Button>
                </div>
              </div>
            </DialogContent>
          </Dialog>
        )}

        <ConfirmDialog
          open={pendingConfirm !== null}
          onOpenChange={(open) => {
            if (!open) setPendingConfirm(null)
          }}
          title={pendingConfirm?.title || 'Please confirm'}
          message={pendingConfirm?.message || ''}
          confirmLabel={pendingConfirm?.confirmLabel || 'Confirm'}
          destructive={pendingConfirm?.destructive || false}
          onConfirm={() => {
            if (pendingConfirm) pendingConfirm.onConfirm()
          }}
        />
      </main>
    </div>
  )
}

function MaintenanceControl() {
  const [enabled, setEnabled] = useState(false)
  const [message, setMessage] = useState('')
  const [estimatedRestore, setEstimatedRestore] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.getMaintenanceMode().then((data) => {
      setEnabled(data.maintenance.active)
      setMessage(data.maintenance.message || '')
      setEstimatedRestore(data.maintenance.estimated_restore || '')
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const handleToggle = async () => {
    setSaving(true)
    try {
      await api.setMaintenanceMode(!enabled, message, estimatedRestore)
      setEnabled(!enabled)
    } catch (err) {
      console.error('Failed to toggle maintenance mode:', err)
    }
    setSaving(false)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.setMaintenanceMode(enabled, message, estimatedRestore)
    } catch (err) {
      console.error('Failed to save maintenance settings:', err)
    }
    setSaving(false)
  }

  if (loading) return <div className="text-sm text-muted-foreground">Loading...</div>

  return (
    <SurfaceCard data-maintenance className="px-5 py-5 sm:px-6">
      <h3 className="text-base font-semibold text-[#102A43]">Maintenance Mode</h3>
      <p className="text-sm text-muted-foreground">Toggle maintenance mode to show a global notification to all users.</p>
      <div className="mt-4 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="font-medium text-[#102A43]">{enabled ? 'Maintenance Mode: ON' : 'Maintenance Mode: OFF'}</p>
            <p className="text-sm text-muted-foreground">
              {enabled ? 'All users see the maintenance banner.' : 'Normal operation.'}
            </p>
          </div>
          <Button
            variant={enabled ? 'destructive' : 'default'}
            onClick={handleToggle}
            disabled={saving}
          >
            {saving ? 'Saving...' : enabled ? 'Disable Maintenance' : 'Enable Maintenance'}
          </Button>
        </div>
        <Field label="Maintenance Message" htmlFor="maintenance-message">
          <Input
            id="maintenance-message"
            type="text"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="SchemeKnit is currently undergoing maintenance. We'll be back shortly."
            className="text-sm"
          />
        </Field>
        <Field label="Estimated Restoration Time" htmlFor="maintenance-restore">
          <Input
            id="maintenance-restore"
            type="text"
            value={estimatedRestore}
            onChange={(e) => setEstimatedRestore(e.target.value)}
            placeholder="e.g. 2 hours, 30 minutes"
            className="text-sm"
          />
        </Field>
        <Button variant="outline" onClick={handleSave} disabled={saving}>
          Save Settings
        </Button>
      </div>
    </SurfaceCard>
  )
}
