'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuth } from '@/lib/auth-context'
import { api } from '@/lib/api'
import { PasswordInput } from '@/components/password-input'
import { validateEmail, validatePassword, PASSWORD_POLICY } from '@/lib/password-policy'
import { GraduationCap } from 'lucide-react'

export default function IndividualSignupPage() {
  const router = useRouter()
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [fullName, setFullName] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    const emailCheck = validateEmail(email)
    if (!emailCheck.ok) {
      setError(emailCheck.message)
      return
    }
    if (!fullName.trim()) {
      setError('Please enter your full name.')
      return
    }
    const pwCheck = validatePassword(password)
    if (!pwCheck.ok) {
      setError(pwCheck.message)
      return
    }

    setError('')
    setLoading(true)

    try {
      const res = await api.registerIndividual(email, password, fullName.trim())
      // The backend returns a token directly; sign the session in.
      if (res.access_token) {
        await login(email, password)
      }
      router.push('/dashboard')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <Card className="w-full max-w-md overflow-hidden">
        <div className="h-2 bg-gradient-to-r from-blue-600 to-blue-500" />
        <CardHeader className="text-center">
          <div className="flex justify-center mb-2">
            <div className="p-3 rounded-full bg-gradient-to-br from-blue-600 to-blue-500 text-white">
              <GraduationCap className="h-7 w-7" />
            </div>
          </div>
          <span className="inline-block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
            Individual Teacher
          </span>
          <CardTitle className="text-2xl">Create your SchemeKnit account</CardTitle>
          <CardDescription>
            Sign up as an individual teacher — no school required. You start on the Free Tier and can upgrade to Pro anytime.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Full name</label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required
                className="w-full px-3 py-2 border rounded-md"
                placeholder="Ama Mensah"
                autoComplete="name"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full px-3 py-2 border rounded-md"
                placeholder="name@gmail.com"
                autoComplete="email"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Password</label>
              <PasswordInput
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                placeholder="Create a password"
                autoComplete="new-password"
                toggleLabel="Show password"
              />
              <p className="mt-1 text-xs text-muted-foreground">
                {PASSWORD_POLICY.description}
              </p>
            </div>

            {error && (
              <p className="text-sm text-destructive bg-destructive/10 p-2 rounded">{error}</p>
            )}

            <Button type="submit" disabled={loading} className="w-full">
              {loading ? 'Please wait...' : 'Create Account'}
            </Button>
          </form>

          <div className="mt-6 p-4 bg-muted rounded-lg">
            <p className="text-sm text-muted-foreground text-center">
              Free Tier includes 3 lesson generations, individual DOCX and PDF export,
              1 custom template and 5 lifetime AI generations.
            </p>
          </div>

          <p className="mt-4 text-center text-sm text-muted-foreground">
            Already have an account?{' '}
            <Link href="/login" className="text-foreground underline">
              Sign in
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
