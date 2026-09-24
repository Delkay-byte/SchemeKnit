'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Key, CheckCircle, AlertCircle, Building2 } from 'lucide-react'
import { api } from '@/lib/api'
import { PasswordInput, PasswordMatchIndicator } from '@/components/password-input'
import { AuthShell } from '@/components/auth/auth-shell'
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
    // The admin signs in normally with the credentials just created (§8).
    // The activation code was an onboarding credential, not a login credential.
    router.push('/login/school-admin')
  }

  const stepMeta =
    step === 'code'
      ? { title: 'Activate Your School', description: 'Enter the activation code provided by SchemeKnit to set up your school workspace.' }
      : step === 'details'
        ? { title: 'Code Valid', description: 'This code activates the following school workspace' }
        : step === 'account'
          ? { title: 'Create School Administrator', description: `Administrator for ${info?.school?.name}. This account manages teachers and settings.` }
          : { title: 'School Activated', description: `${info?.school?.name} is active. Sign in as ${createdEmail} to open your workspace.` }

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
      <Card className="w-full border-0 shadow-none">
        {step === 'code' && (
          <>
            <CardHeader className="text-center px-0 pt-0">
              <Key className="h-12 w-12 text-primary mx-auto mb-4" />
            </CardHeader>
            <CardContent className="px-0 pb-0">
              <form onSubmit={handleValidate} className="space-y-4">
                {error && (
                  <div className="p-3 text-sm text-destructive bg-destructive/10 rounded-md flex items-start gap-2">
                    <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                    <span>{error}</span>
                  </div>
                )}
                <div className="space-y-2">
                  <label className="block text-sm font-medium">Activation Code</label>
                  <input
                    type="text"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    placeholder="TF-SCH-XXXX-XXXX-XXXX"
                    required
                    className="w-full px-3 py-2 border rounded-md font-mono text-center text-lg tracking-wider"
                  />
                </div>
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading ? 'Validating...' : 'Validate Code'}
                </Button>
              </form>
            </CardContent>
          </>
        )}

        {step === 'details' && info && (
          <>
            <CardHeader className="text-center px-0 pt-0">
              <Building2 className="h-12 w-12 text-primary mx-auto mb-4" />
            </CardHeader>
            <CardContent className="px-0 pb-0 space-y-4">
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">School:</span>
                  <span className="font-medium">{info.school?.name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Plan:</span>
                  <span className="font-medium">{info.license?.plan}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">License status:</span>
                  <span className="font-medium">{info.license?.status}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Teacher seats:</span>
                  <span className="font-medium">{info.license?.seat_limit}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Valid until:</span>
                  <span className="font-medium">{info.license?.expiry_date}</span>
                </div>
              </div>
              <Button className="w-full" onClick={() => setStep('account')}>
                Continue — Create School Administrator
              </Button>
              <Button variant="ghost" className="w-full" onClick={() => setStep('code')}>
                Use a different code
              </Button>
            </CardContent>
          </>
        )}

        {step === 'account' && (
          <>
            <CardContent className="px-0 pb-0">
              <form onSubmit={handleCreateAdmin} className="space-y-4">
                {error && (
                  <div className="p-3 text-sm text-destructive bg-destructive/10 rounded-md">{error}</div>
                )}
                <div className="space-y-2">
                  <label className="block text-sm font-medium">Full Name</label>
                  <input type="text" value={name} onChange={(e) => setName(e.target.value)}
                    placeholder="Ama Serwaa" required className="w-full px-3 py-2 border rounded-md" />
                </div>
                <div className="space-y-2">
                  <label className="block text-sm font-medium">Email</label>
                  <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                    placeholder="admin@school.edu.gh" required className="w-full px-3 py-2 border rounded-md" />
                </div>
                <div className="space-y-2">
                  <label className="block text-sm font-medium">Password (min 8 characters)</label>
                  <PasswordInput value={password} onChange={(e) => setPassword(e.target.value)}
                    required toggleLabel="Show password" placeholder="At least 8 characters" />
                  <p className="text-xs text-muted-foreground">{PASSWORD_POLICY.description}</p>
                </div>
                <div className="space-y-2">
                  <label className="block text-sm font-medium">Confirm Password</label>
                  <PasswordInput value={confirm} onChange={(e) => setConfirm(e.target.value)}
                    required toggleLabel="Show password" placeholder="Confirm password" />
                  <PasswordMatchIndicator password={password} confirm={confirm} />
                </div>
                <Button type="submit" className="w-full" disabled={creating}>
                  {creating ? 'Creating Account...' : 'Create Administrator'}
                </Button>
              </form>
            </CardContent>
          </>
        )}

        {step === 'done' && (
          <>
            <CardHeader className="text-center px-0 pt-0">
              <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-4" />
            </CardHeader>
            <CardContent className="px-0 pb-0">
              <Button className="w-full" onClick={handleEnter}>
                Go to Sign In
              </Button>
            </CardContent>
          </>
        )}
      </Card>
    </AuthShell>
  )
}
