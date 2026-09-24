'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { BookOpen, Key, CheckCircle, AlertCircle } from 'lucide-react'
import { api } from '@/lib/api'
import { PasswordInput, PasswordMatchIndicator } from '@/components/password-input'
import { AuthShell } from '@/components/auth/auth-shell'
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
      ? { title: 'SchemeKnit Activated', description: 'Your school license is active. Create the school administrator to continue.' }
      : step === 'create-admin'
        ? { title: 'Create School Administrator', description: `Set up the administrator for ${activationResult?.school?.name || 'your school'}` }
        : { title: 'Welcome to SchemeKnit', description: 'This installation requires a school license to unlock licensed features.' }

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
      <Card className="w-full border-0 shadow-none">
        {step === 'success' && activationResult && (
          <>
            <CardHeader className="text-center px-0 pt-0">
              <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-4" />
            </CardHeader>
            <CardContent className="px-0 pb-0 space-y-4">
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">School:</span>
                  <span className="font-medium">{activationResult.school?.name || 'Unknown'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Plan:</span>
                  <span className="font-medium">{activationResult.license?.plan || 'Unknown'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Valid Until:</span>
                  <span className="font-medium">{activationResult.license?.expiry_date || 'Unknown'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Teacher Seats:</span>
                  <span className="font-medium">{activationResult.license?.seat_limit || 0}</span>
                </div>
              </div>
              <Button className="w-full" onClick={() => setStep('create-admin')}>
                Create School Administrator
              </Button>
            </CardContent>
          </>
        )}

        {step === 'create-admin' && (
          <>
            <CardHeader className="text-center px-0 pt-0">
              <BookOpen className="h-12 w-12 text-primary mx-auto mb-4" />
            </CardHeader>
            <CardContent className="px-0 pb-0">
              <form onSubmit={handleCreateAdmin} className="space-y-4">
                {adminError && (
                  <div className="p-3 text-sm text-destructive bg-destructive/10 rounded-md">
                    {adminError}
                  </div>
                )}
                <div className="space-y-2">
                  <label className="block text-sm font-medium">Full Name</label>
                  <input
                    type="text"
                    value={adminName}
                    onChange={(e) => setAdminName(e.target.value)}
                    placeholder="Kwame Asante"
                    required
                    className="w-full px-3 py-2 border rounded-md"
                  />
                </div>
                <div className="space-y-2">
                  <label className="block text-sm font-medium">Email</label>
                  <input
                    type="email"
                    value={adminEmail}
                    onChange={(e) => setAdminEmail(e.target.value)}
                    placeholder="admin@school.edu.gh"
                    required
                    className="w-full px-3 py-2 border rounded-md"
                  />
                </div>
                <div className="space-y-2">
                  <label className="block text-sm font-medium">Password</label>
                  <PasswordInput
                    value={adminPassword}
                    onChange={(e) => setAdminPassword(e.target.value)}
                    placeholder="At least 8 characters"
                    required
                    toggleLabel="Show password"
                  />
                  <p className="text-xs text-muted-foreground">{PASSWORD_POLICY.description}</p>
                </div>
                <div className="space-y-2">
                  <label className="block text-sm font-medium">Confirm Password</label>
                  <PasswordInput
                    value={adminConfirm}
                    onChange={(e) => setAdminConfirm(e.target.value)}
                    placeholder="Confirm password"
                    required
                    toggleLabel="Show password"
                  />
                  <PasswordMatchIndicator password={adminPassword} confirm={adminConfirm} />
                </div>
                <Button type="submit" className="w-full" disabled={adminLoading}>
                  {adminLoading ? 'Creating Account...' : 'Create Administrator'}
                </Button>
              </form>
            </CardContent>
          </>
        )}

        {step === 'input' && (
          <>
            <CardHeader className="text-center px-0 pt-0">
              <Key className="h-12 w-12 text-primary mx-auto mb-4" />
            </CardHeader>
            <CardContent className="px-0 pb-0">
              <form onSubmit={handleActivate} className="space-y-4">
                {error && (
                  <div className="p-3 text-sm text-destructive bg-destructive/10 rounded-md flex items-start gap-2">
                    <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                    <span>{error}</span>
                  </div>
                )}
                <div className="space-y-2">
                  <label className="block text-sm font-medium">License / Activation Code</label>
                  <input
                    type="text"
                    value={activationCode}
                    onChange={(e) => setActivationCode(e.target.value)}
                    placeholder="TF-SCH-XXXX-XXXX-XXXX"
                    required
                    className="w-full px-3 py-2 border rounded-md font-mono text-center text-lg tracking-wider"
                  />
                </div>
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading ? 'Activating...' : 'Activate SchemeKnit'}
                </Button>
                <Button type="button" variant="ghost" className="w-full" onClick={handleFreeOffline}>
                  Continue with Free Offline
                </Button>
              </form>
            </CardContent>
          </>
        )}
      </Card>
    </AuthShell>
  )
}
