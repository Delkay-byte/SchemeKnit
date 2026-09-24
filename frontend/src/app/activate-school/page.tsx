'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Key, CheckCircle, AlertCircle, Building2, ArrowRight } from 'lucide-react'
import { api } from '@/lib/api'
import { PasswordInput, PasswordMatchIndicator } from '@/components/password-input'
import { AuthShell } from '@/components/auth/auth-shell'
import { AuthField, AuthError } from '@/components/auth/auth-field'
import {
  validatePassword, validateEmail, PASSWORD_POLICY,
} from '@/lib/password-policy'

type Step = 'code' | 'details' | 'account' | 'done'

export default function ActivateSchoolPage() {
  const router = useRouter()
  const [step, setStep] = useState<Step>('code')
  const [code, setCode] = useState('')
  const [info, setInfo] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [creating, setCreating] = useState(false)
  const [createdEmail, setCreatedEmail] = useState('')

  const handleValidate = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!code.trim()) {
      setError('Please enter your activation code')
      return
    }
    setLoading(true)
    try {
      const res = await api.validateActivationCode(code.trim())
      setInfo(res)
      setStep('details')
    } catch (err: any) {
      const msg = err.message || 'Activation failed'
      if (msg.includes('Invalid')) setError('Invalid activation code. Please check and try again.')
      else if (msg.includes('revoked')) setError('This activation code has been revoked. Contact SchemeKnit support.')
      else if (msg.includes('expired') || msg.includes('Expired')) setError('This code or its license has expired. Contact SchemeKnit to renew.')
      else if (msg.includes('already used')) setError('This activation code has already been used.')
      else if (msg.includes('suspended') || msg.includes('cancelled')) setError('The license for this code is not active. Contact SchemeKnit support.')
      else setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleCreateAdmin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    const emailCheck = validateEmail(email)
    if (!emailCheck.ok) {
      setError(emailCheck.message)
      return
    }
    const pwCheck = validatePassword(password)
    if (!pwCheck.ok) {
      setError(pwCheck.message)
      return
    }
    if (password !== confirm) {
      setError('Passwords do not match')
      return
    }
    setCreating(true)
    try {
      await api.setupAfterActivation({
        email,
        password,
        full_name: name,
        activation_code: code.trim(),
      })
      setCreatedEmail(email)
      setStep('done')
    } catch (err: any) {
      const msg = err.message || 'Failed to create administrator'
      if (msg.includes('already used')) setError('This activation code has already been used.')
      else if (msg.includes('registered')) setError('An account with this email already exists.')
      else setError(msg)
    } finally {
      setCreating(false)
    }
  }

  const handleEnter = () => {
    router.push('/login/school-admin')
  }

  const stepMeta =
    step === 'code'
      ? { title: 'Activate your school', description: 'Connect your school to SchemeKnit and begin managing your teaching team. Enter the activation code provided by SchemeKnit.' }
      : step === 'details'
        ? { title: 'Code valid', description: 'This code activates the following school workspace. Review the details before continuing.' }
        : step === 'account'
          ? { title: 'Create school administrator', description: `Administrator for ${info?.school?.name}. This account manages teachers and settings.` }
          : { title: 'School activated', description: `${info?.school?.name} is active. Sign in as ${createdEmail} to open your workspace.` }

  return (
    <AuthShell
      role="school_activate"
      title={stepMeta.title}
      description={stepMeta.description}
      steps={[
        { label: 'Activation code', done: step !== 'code', active: step === 'code' },
        { label: 'Review license', done: step !== 'details' && step !== 'code', active: step === 'details' },
        { label: 'Admin account', done: step === 'done', active: step === 'account' },
        { label: 'Done', done: step === 'done', active: step === 'done' },
      ]}
    >
      {step === 'code' && (
        <form onSubmit={handleValidate} className="space-y-4" noValidate>
          <div className="rounded-xl border border-[#04A9CE]/25 bg-[#04A9CE]/8 px-4 py-3 text-center shadow-sm">
            <Key className="mx-auto h-5 w-5 text-[#04A9CE]" aria-hidden="true" />
            <p className="mt-1.5 text-[11px] font-bold uppercase tracking-[0.16em] text-[#0389a8]">
              Institutional activation code
            </p>
          </div>
          <AuthField id="school-activation-code" label="Activation code">
            <Input
              id="school-activation-code"
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value)}
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
                Validating…
              </span>
            ) : (
              <span className="inline-flex items-center gap-2">
                Validate code
                <ArrowRight className="h-4 w-4" aria-hidden="true" />
              </span>
            )}
          </Button>
        </form>
      )}

      {step === 'details' && info && (
        <div className="space-y-4">
          <div className="rounded-xl border border-border bg-[#F4F7FA] p-4 shadow-sm">
            <div className="mb-3 flex items-center gap-2">
              <Building2 className="h-4 w-4 text-[#04A9CE]" aria-hidden="true" />
              <p className="text-[11px] font-bold uppercase tracking-wider text-[#04A9CE]">License details</p>
            </div>
            <dl className="space-y-2.5 text-sm">
              {[
                ['School', info.school?.name],
                ['Plan', info.license?.plan],
                ['License status', info.license?.status],
                ['Teacher seats', String(info.license?.seat_limit ?? '—')],
                ['Valid until', info.license?.expiry_date],
              ].map(([k, v]) => (
                <div key={k} className="flex items-center justify-between gap-3 border-b border-border/60 pb-2 last:border-0 last:pb-0">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd className="font-semibold text-[#102A43] text-right">{v ?? '—'}</dd>
                </div>
              ))}
            </dl>
          </div>
          <Button
            onClick={() => setStep('account')}
            className="h-11 w-full rounded-lg bg-[#102A43] text-white font-semibold shadow-[0_4px_14px_rgba(16,42,67,0.25)] hover:bg-[#0d2740] active:scale-[0.98] transition"
          >
            Continue — Create school administrator
          </Button>
          <Button
            variant="ghost"
            className="w-full"
            onClick={() => setStep('code')}
          >
            Use a different code
          </Button>
        </div>
      )}

      {step === 'account' && (
        <form onSubmit={handleCreateAdmin} className="space-y-4" noValidate>
          <AuthField id="school-admin-name" label="Full name">
            <Input
              id="school-admin-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ama Serwaa"
              required
              autoComplete="name"
              aria-invalid={error ? true : undefined}
            />
          </AuthField>
          <AuthField id="school-admin-email" label="Email">
            <Input
              id="school-admin-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@school.edu.gh"
              required
              autoComplete="email"
              aria-invalid={error ? true : undefined}
            />
          </AuthField>
          <AuthField
            id="school-admin-password"
            label="Password"
            hint={PASSWORD_POLICY.description}
          >
            <PasswordInput
              id="school-admin-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              toggleLabel="Show password"
              placeholder="At least 8 characters"
              autoComplete="new-password"
            />
          </AuthField>
          <AuthField id="school-admin-confirm" label="Confirm password">
            <PasswordInput
              id="school-admin-confirm"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              toggleLabel="Show password"
              placeholder="Confirm password"
              autoComplete="new-password"
            />
          </AuthField>
          <PasswordMatchIndicator password={password} confirm={confirm} />
          <AuthError message={error} />
          <Button
            type="submit"
            disabled={creating}
            className="h-11 w-full rounded-lg bg-[#102A43] text-white font-semibold shadow-[0_4px_14px_rgba(16,42,67,0.25)] hover:bg-[#0d2740] active:scale-[0.98] transition disabled:opacity-60"
          >
            {creating ? (
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

      {step === 'done' && (
        <div className="space-y-4 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-100 shadow-inner">
            <CheckCircle className="h-8 w-8 text-emerald-600" aria-hidden="true" />
          </div>
          <p className="text-sm text-muted-foreground leading-relaxed">
            {info?.school?.name} is active. Sign in as{' '}
            <strong className="text-[#102A43]">{createdEmail}</strong> to open
            your workspace.
          </p>
          <Button
            onClick={handleEnter}
            className="h-11 w-full rounded-lg bg-[#102A43] text-white font-semibold shadow-[0_4px_14px_rgba(16,42,67,0.25)] hover:bg-[#0d2740] active:scale-[0.98] transition"
          >
            <span className="inline-flex items-center gap-2">
              Go to sign in
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </span>
          </Button>
        </div>
      )}
    </AuthShell>
  )
}
