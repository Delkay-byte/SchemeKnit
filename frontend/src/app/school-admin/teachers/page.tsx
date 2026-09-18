'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { UserPlus, Pencil, Key, KeyRound, UserCheck, UserX, X, Copy, Check } from 'lucide-react'
import { api } from '@/lib/api'
import { PasswordInput } from '@/components/password-input'
import { validatePassword, validateEmail, PASSWORD_POLICY } from '@/lib/password-policy'

interface Teacher {
  id: string
  email: string
  full_name: string
  is_active: boolean
  role?: string
}

export default function TeachersPage() {
  const [teachers, setTeachers] = useState<Teacher[]>([])
  const [seats, setSeats] = useState<{ used: number; limit: number } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionId, setActionId] = useState<string | null>(null)

  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ email: '', password: '', full_name: '' })
  const [editing, setEditing] = useState<Teacher | null>(null)
  const [editForm, setEditForm] = useState({ full_name: '', email: '' })
  const [resetId, setResetId] = useState<string | null>(null)
  const [newPassword, setNewPassword] = useState('')

  // Token-based initiate-reset
  const [pwResetResult, setPwResetResult] = useState<{
    token: string
    email: string
    minutes: number
  } | null>(null)
  const [copiedToken, setCopiedToken] = useState(false)

  useEffect(() => {
    load()
  }, [])

  const load = async () => {
    try {
      setLoading(true)
      setError(null)
      const [usersRes, school] = await Promise.all([api.listUsers(), api.getMySchool()])
      setTeachers((usersRes.users || []).filter((u: Teacher) => u.role === 'teacher'))
      setSeats(school.seats || null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load teachers')
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async () => {
    const emailCheck = validateEmail(form.email)
    if (!form.full_name.trim() || !emailCheck.ok) {
      setError('Provide a name and a valid email address')
      return
    }
    const pwCheck = validatePassword(form.password)
    if (!pwCheck.ok) {
      setError(pwCheck.message)
      return
    }
    try {
      setActionId('create')
      setError(null)
      await api.createTeacher(form)
      setShowCreate(false)
      setForm({ email: '', password: '', full_name: '' })
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Create teacher failed')
    } finally {
      setActionId(null)
    }
  }

  const handleToggle = async (t: Teacher) => {
    const verb = t.is_active ? 'deactivate' : 'reactivate'
    if (!confirm(`${t.is_active ? 'Deactivate' : 'Reactivate'} ${t.full_name} (${t.email})?`)) return
    try {
      setActionId(t.id)
      setError(null)
      await api.toggleUserActive(t.id)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : `${verb} failed`)
    } finally {
      setActionId(null)
    }
  }

  const openEdit = (t: Teacher) => {
    setEditing(t)
    setEditForm({ full_name: t.full_name, email: t.email })
  }

  const handleEdit = async () => {
    if (!editing) return
    try {
      setActionId(editing.id)
      setError(null)
      await api.updateTeacher(editing.id, editForm)
      setEditing(null)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Update failed')
    } finally {
      setActionId(null)
    }
  }

  const handleResetPassword = async () => {
    if (!resetId) return
    const pwCheck = validatePassword(newPassword)
    if (!pwCheck.ok) {
      setError(pwCheck.message)
      return
    }
    try {
      setActionId(resetId)
      setError(null)
      await api.resetUserPassword(resetId, newPassword)
      setResetId(null)
      setNewPassword('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Password reset failed')
    } finally {
      setActionId(null)
    }
  }

  const handleInitiateReset = async (t: Teacher) => {
    if (!confirm(`You are about to initiate a password reset for ${t.full_name} (${t.email}).\n\nA one-time reset token will be generated. Continue?`)) {
      return
    }
    try {
      setActionId(t.id)
      setError(null)
      const res = await api.initiatePasswordReset(t.id)
      setPwResetResult({
        token: res.reset_token,
        email: res.target_email,
        minutes: res.expires_in_minutes,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to initiate reset')
    } finally {
      setActionId(null)
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

  const seatsFull = seats != null && seats.used >= seats.limit

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Teachers ({teachers.length})</h1>
          <p className="text-muted-foreground text-sm">
            {seats != null
              ? `Seats used: ${seats.used} of ${seats.limit}`
              : 'Seat usage unavailable'}
          </p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <UserPlus className="h-4 w-4 mr-1.5" />
          Add Teacher
        </Button>
      </div>

      {error && (
        <div className="p-4 bg-destructive/10 border border-destructive/20 rounded-lg">
          <p className="text-destructive text-sm">{error}</p>
        </div>
      )}

      {seatsFull && (
        <div className="p-4 bg-orange-50 border border-orange-200 rounded-lg text-sm text-orange-800">
          Seat limit reached ({seats?.used}/{seats?.limit}). Deactivate a teacher to free a seat,
          or contact SchemeKnit to upgrade the school license. Deactivated teachers keep their data
          but cannot sign in.
        </div>
      )}

      {teachers.length === 0 ? (
        <Card>
          <CardContent className="p-12 text-center">
            <p className="text-lg font-medium mb-2">No teachers yet</p>
            <p className="text-muted-foreground mb-4">
              Add your first teacher so they can start creating lesson plans.
            </p>
            <Button onClick={() => setShowCreate(true)}>Add Teacher</Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left p-3 font-medium">Name</th>
                    <th className="text-left p-3 font-medium">Email</th>
                    <th className="text-left p-3 font-medium">Status</th>
                    <th className="text-right p-3 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {teachers.map((t) => (
                    <tr key={t.id} className="border-b hover:bg-muted/30">
                      <td className="p-3">{t.full_name}</td>
                      <td className="p-3 text-muted-foreground">{t.email}</td>
                      <td className="p-3">
                        <span className={`px-2 py-0.5 rounded-full text-xs ${t.is_active ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                          {t.is_active ? 'active' : 'inactive'}
                        </span>
                      </td>
                      <td className="p-3">
                        <div className="flex justify-end gap-1">
                          <Button size="sm" variant="ghost" onClick={() => openEdit(t)} title="Edit">
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => handleToggle(t)}
                            disabled={actionId === t.id} title={t.is_active ? 'Deactivate' : 'Reactivate'}>
                            {t.is_active ? <UserX className="h-4 w-4" /> : <UserCheck className="h-4 w-4" />}
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setResetId(t.id)} title="Reset password">
                            <Key className="h-4 w-4" />
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => handleInitiateReset(t)}
                            disabled={actionId === t.id} title="Initiate password reset (one-time token)">
                            <KeyRound className="h-4 w-4" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {showCreate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setShowCreate(false)}>
          <Card className="max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            <CardHeader>
              <CardTitle>Add Teacher</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <input type="text" placeholder="Full name" value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                className="w-full px-3 py-2 border rounded-md" />
              <input type="email" placeholder="Email" value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="w-full px-3 py-2 border rounded-md" />
              <PasswordInput placeholder="Temporary password" value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                toggleLabel="Show password" />
              <p className="text-xs text-muted-foreground">{PASSWORD_POLICY.description}</p>
              <div className="flex gap-2">
                <Button onClick={handleCreate} disabled={actionId === 'create'}>
                  {actionId === 'create' ? 'Adding...' : 'Add Teacher'}
                </Button>
                <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {editing && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setEditing(null)}>
          <Card className="max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            <CardHeader>
              <CardTitle>Edit Teacher</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <input type="text" placeholder="Full name" value={editForm.full_name}
                onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })}
                className="w-full px-3 py-2 border rounded-md" />
              <input type="email" placeholder="Email" value={editForm.email}
                onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                className="w-full px-3 py-2 border rounded-md" />
              <div className="flex gap-2">
                <Button onClick={handleEdit} disabled={actionId === editing.id}>Save</Button>
                <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {resetId && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setResetId(null)}>
          <Card className="max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            <CardHeader>
              <CardTitle>Reset Password</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <PasswordInput placeholder="New password" value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                toggleLabel="Show password" />
              <p className="text-xs text-muted-foreground">{PASSWORD_POLICY.description}</p>
              <div className="flex gap-2">
                <Button onClick={handleResetPassword} disabled={actionId === resetId}>Reset</Button>
                <Button variant="outline" onClick={() => setResetId(null)}>
                  <X className="h-4 w-4 mr-1" /> Cancel
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {pwResetResult && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setPwResetResult(null)}>
          <Card className="max-w-lg w-full" onClick={(e) => e.stopPropagation()}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <KeyRound className="h-5 w-5" />
                Password Reset Token
              </CardTitle>
              <CardDescription>
                For <strong>{pwResetResult.email}</strong> — expires in {pwResetResult.minutes} minutes.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <p className="text-sm text-amber-800">
                  This token is shown <strong>once</strong>. Deliver it to the
                  teacher out-of-band (phone, in person). They complete the reset
                  at <strong>/reset-password</strong>.
                </p>
              </div>
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
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
