'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Key, CheckCircle, AlertCircle, ArrowRight, Sparkles } from 'lucide-react'
import { api } from '@/lib/api'
import { PasswordInput, PasswordMatchIndicator } from '@/components/password-input'
import { AuthShell } from '@/components/auth/auth-shell'
import { AuthField, AuthError } from '@/components/auth/auth-field'
import { validatePassword, validateEmail, PASSWORD_POLICY } from '@/lib/password-policy'

type ActivationStep = 'input' | 'success' | 'create-admin'

export default function ActivatePage() {
  const router = useRouter()
  const [step, setStep] = useState<ActivationStep>('input')
  const [activationCode, setActivationCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [activationResult, setActivationResult] = useState<any>(null)

  const [adminName, setAdminName] = useState('')
  const [adminEmail, setAdminEmail] = useState('')
  const [adminPassword, setAdminPassword] = useState('')
  const [adminConfirm, setAdminConfirm] = useState('')
  const [adminLoading, setAdminLoading] = useState(false)
  const [adminError, setAdminError] = useState('')

  const handleActivate = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!activationCode.trim()) {
      setError('Please enter your activation code')
      return
    }
    setLoading(true)
    try {
      const result = await api.activateDesktop(activationCode.trim())
      setActivationResult(result)
      setStep('success')
    } catch (err: any) {
      const msg = err.message || 'Activation failed'
      if (msg.includes('Invalid')) setError('Invalid activation code. Please check and try again.')
      else if (msg.includes('revoked')) setError('This activation code has been revoked. Contact SchemeKnit support.')
      else if (msg.includes('expired')) setError('This activation code has expired. Contact SchemeKnit to renew.')
      else if (msg.includes('already used')) setError('This activation code has already been used.')
      else if (msg.includes('Suspended') || msg.includes('suspended')) setError('The license for this code has been suspended. Contact SchemeKnit support.')
      else setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleCreateAdmin = async (e: React.FormEvent) => {
    e.preventDefault()
    setAdminError('')
    const emailCheck = validateEmail(adminEmail)
    if (!emailCheck.ok) {
      setAdminError(emailCheck.message)
      return
    }
    const pwCheck = validatePassword(adminPassword)
    if (!pwCheck.ok) {
      setAdminError(pwCheck.message)
      return
    }
    if (adminPassword !== adminConfirm) {
      setAdminError('Passwords do not match')
      return
    }
    setAdminLoading(true)
    try {
      await api.setupAfterActivation({
        email: adminEmail,
        password: adminPassword,
        full_name: adminName,
        activation_code: activationCode.trim(),
        school_id: activationResult?.school?.id,
      })
      router.push('/login')
    } catch (err: any) {
      setAdminError(err.message || 'Failed to create administrator')
    } finally {
      setAdminLoading(false)
    }
  }

  const handleFreeOffline = () => {
    router.push('/login')
  }

  const stepMeta =
    step === 'success'
      ? { title: 'License unlocked', description: 'Your SchemeKnit license is active. Create the school administrator to continue.' }
      : step === 'create-admin'
        ? { title: 'Create school administrator', description: `Set up the administrator for ${activationResult?.school?.name || 'your school'}` }
        : { title: 'Activate your license', description: 'Unlock your teaching tools. Enter the license code included with your SchemeKnit installation.' }

  return (
    <AuthShell
      role="teacher_license"
      title={stepMeta.title}
      description={stepMeta.description}
      steps={[
        { label: 'Activation code', done: step !== 'input', active: step === 'input' },
        { label: 'Confirm license', done: step === 'success' || step === 'create-admin', active: step === 'success' },
        { label: 'Administrator', done: false, active: step === 'create-admin' },
      ]}
    >
      {step === 'input' && (
        <form onSubmit={handleActivate} className="space-y-4" noValidate>
          <div className="rounded-xl border border-amber-200/80 bg-gradient-to-r from-amber-50 to-[#FFF8EC] px-4 py-3 shadow-sm">
            <div className="flex items-center justify-center gap-2">
              <Sparkles className="h-4 w-4 text-amber-600" aria-hidden="true" />
              <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-amber-700">
                Personal entitlement
              </p>
            </div>
            <p className="mt-1 text-center text-xs text-amber-800/70">
              Free Tier → activated plan
            </p>
          </div>
          <AuthField id="license-activation-code" label="License / activation code">
            <Input
              id="license-activation-code"
              type="text"
              value={activationCode}
              onChange={(e) => setActivationCode(e.target.value)}
              placeholder="TF-SCH-XXXX-XXXX-XXXX"
              required
              autoComplete="off"
              aria-invalid={error ? true : undefined}
              className="h-12 text-center font-mono text-base tracking-[0.2em] shadow-inner"
            />
          </AuthField>
          <AuthError message={error} />
          <Button
            type="submit"
            disabled={loading}
            className="h-11 w-full rounded-lg bg-[#102A43] text-white font-semibold shadow-[0_4px_14px_rgba(16,42,67,0.25)] hover:bg-[#0d2740] active:scale-[0.98] transition focus-visible:ring-2 focus-visible:ring-[#04A9CE] focus-visible:ring-offset-2 disabled:opacity-60"
          >
            {loading ? (
              <span className="inline-flex items-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                Activating…
              </span>
            ) : (
              <span className="inline-flex items-center gap-2">
                Activate license
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </span>
            )}
          </Button>
          <Button
            type="button"
            variant="ghost"
            className="w-full"
            onClick={handleFreeOffline}
          >
            Continue with Free Offline
          </Button>
        </form>
      )}

      {step === 'success' && activationResult && (
        <div className="space-y-4">
          <div className="rounded-xl border border-emerald-200 bg-emerald-50/80 p-4 text-center shadow-sm">
            <CheckCircle className="mx-auto h-8 w-8 text-emerald-600" aria-hidden="true" />
            <p className="mt-2 text-sm font-semibold text-emerald-800">License confirmed</p>
          </div>
          <div className="rounded-xl border border-border bg-[#FAFAF7] p-4 shadow-sm">
            <dl className="space-y-2.5 text-sm">
              {[
                ['School', activationResult.school?.name || 'Unknown'],
                ['Plan', activationResult.license?.plan || 'Unknown'],
                ['Valid until', activationResult.license?.expiry_date || 'Unknown'],
                ['Teacher seats', String(activationResult.license?.seat_limit ?? 0)],
              ].map(([k, v]) => (
                <div key={k} className="flex items-center justify-between gap-3 border-b border-border/60 pb-2 last:border-0 last:pb-0">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd className="font-semibold text-[#102A43] text-right">{v}</dd>
                </div>
              ))}
            </dl>
          </div>
          <Button
            onClick={() => setStep('create-admin')}
            className="h-11 w-full rounded-lg bg-[#102A43] text-white font-semibold shadow-[0_4px_14px_rgba(16,42,67,0.25)] hover:bg-[#0d2740] active:scale-[0.98] transition"
          >
            Create school administrator
          </Button>
        </div>
      )}

      {step === 'create-admin' && (
        <form onSubmit={handleCreateAdmin} className="space-y-4" noValidate>
          <AuthField id="lic-admin-name" label="Full name">
            <Input
              id="lic-admin-name"
              type="text"
              value={adminName}
              onChange={(e) => setAdminName(e.target.value)}
              placeholder="Kwame Asante"
              required
              autoComplete="name"
              aria-invalid={adminError ? true : undefined}
            />
          </AuthField>
          <AuthField id="lic-admin-email" label="Email">
            <Input
              id="lic-admin-email"
              type="email"
              value={adminEmail}
              onChange={(e) => setAdminEmail(e.target.value)}
              placeholder="admin@school.edu.gh"
              required
              autoComplete="email"
              aria-invalid={adminError ? true : undefined}
            />
          </AuthField>
          <AuthField
            id="lic-admin-password"
            label="Password"
            hint={PASSWORD_POLICY.description}
          >
            <PasswordInput
              id="lic-admin-password"
              value={adminPassword}
              onChange={(e) => setAdminPassword(e.target.value)}
              placeholder="At least 8 characters"
              required
              toggleLabel="Show password"
              autoComplete="new-password"
            />
          </AuthField>
          <AuthField id="lic-admin-confirm" label="Confirm password">
            <PasswordInput
              id="lic-admin-confirm"
              value={adminConfirm}
              onChange={(e) => setAdminConfirm(e.target.value)}
              placeholder="Confirm password"
              required
              toggleLabel="Show password"
              autoComplete="new-password"
            />
          </AuthField>
          <PasswordMatchIndicator password={adminPassword} confirm={adminConfirm} />
          <AuthError message={adminError} />
          <Button
            type="submit"
            disabled={adminLoading}
            className="h-11 w-full rounded-lg bg-[#102A43] text-white font-semibold shadow-[0_4px_14px_rgba(16,42,67,0.25)] hover:bg-[#0d2740] active:scale-[0.98] transition disabled:opacity-60"
          >
            {adminLoading ? (
              <span className="inline-flex items-center gap-2">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                Creating account…
              </span>
            ) : (
              'Create administrator'
            )}
          </Button>
        </form>
      )}
    </AuthShell>
  )
}
