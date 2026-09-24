'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
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
import { UserPlus, Pencil, Key, KeyRound, UserCheck, UserX, X, Copy, Check } from 'lucide-react'
import { api } from '@/lib/api'
import { PageHeader } from '@/components/ui/page-header'
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

  const [pendingToggle, setPendingToggle] = useState<Teacher | null>(null)
  const [pendingInitReset, setPendingInitReset] = useState<Teacher | null>(null)

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

  const runToggle = async (t: Teacher) => {
    const verb = t.is_active ? 'deactivate' : 'reactivate'
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

  const runInitiateReset = async (t: Teacher) => {
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
      <PageHeader
        title={`Teachers (${teachers.length})`}
        description={
          seats != null
            ? `Seats used: ${seats.used} of ${seats.limit}`
            : 'Seat usage unavailable'
        }
        actions={
          <Button onClick={() => setShowCreate(true)}>
            <UserPlus className="h-4 w-4 mr-1.5" />
            Add Teacher
          </Button>
        }
      />

      {error && <Banner tone="danger">{error}</Banner>}

      {seatsFull && (
        <Banner tone="warning">
          Seat limit reached ({seats?.used}/{seats?.limit}). Deactivate a teacher to free a seat,
          or contact SchemeKnit to upgrade the school license. Deactivated teachers keep their data
          but cannot sign in.
        </Banner>
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
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/50 hover:bg-muted/50">
                  <TableHead>Name</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {teachers.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell>{t.full_name}</TableCell>
                    <TableCell className="text-muted-foreground">{t.email}</TableCell>
                    <TableCell>
                      <StatusPill tone={t.is_active ? 'success' : 'danger'} className="rounded-full">
                        {t.is_active ? 'active' : 'inactive'}
                      </StatusPill>
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button size="sm" variant="ghost" onClick={() => openEdit(t)} title="Edit">
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setPendingToggle(t)}
                          disabled={actionId === t.id} title={t.is_active ? 'Deactivate' : 'Reactivate'}>
                          {t.is_active ? <UserX className="h-4 w-4" /> : <UserCheck className="h-4 w-4" />}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setResetId(t.id)} title="Reset password">
                          <Key className="h-4 w-4" />
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setPendingInitReset(t)}
                          disabled={actionId === t.id} title="Initiate password reset (one-time token)">
                          <KeyRound className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {showCreate && (
        <Dialog open onOpenChange={setShowCreate}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Add Teacher</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <Input type="text" placeholder="Full name" value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
              <Input type="email" placeholder="Email" value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })} />
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
            </div>
          </DialogContent>
        </Dialog>
      )}

      {editing && (
        <Dialog open onOpenChange={(open) => { if (!open) setEditing(null) }}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Edit Teacher</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <Input type="text" placeholder="Full name" value={editForm.full_name}
                onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })} />
              <Input type="email" placeholder="Email" value={editForm.email}
                onChange={(e) => setEditForm({ ...editForm, email: e.target.value })} />
              <div className="flex gap-2">
                <Button onClick={handleEdit} disabled={actionId === editing.id}>Save</Button>
                <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      )}

      {resetId && (
        <Dialog open onOpenChange={(open) => { if (!open) setResetId(null) }}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Reset Password</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
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
            </div>
          </DialogContent>
        </Dialog>
      )}

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
                teacher out-of-band (phone, in person). They complete the reset
                at <strong>/reset-password</strong>.
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
        open={pendingToggle !== null}
        onOpenChange={(open) => {
          if (!open) setPendingToggle(null)
        }}
        title={pendingToggle?.is_active ? 'Deactivate teacher' : 'Reactivate teacher'}
        message={
          pendingToggle
            ? `${pendingToggle.is_active ? 'Deactivate' : 'Reactivate'} ${pendingToggle.full_name} (${pendingToggle.email})?`
            : ''
        }
        confirmLabel="Continue"
        destructive={!!pendingToggle?.is_active}
        onConfirm={() => {
          if (pendingToggle !== null) runToggle(pendingToggle)
        }}
      />

      <ConfirmDialog
        open={pendingInitReset !== null}
        onOpenChange={(open) => {
          if (!open) setPendingInitReset(null)
        }}
        title="Initiate password reset"
        message={
          pendingInitReset
            ? `You are about to initiate a password reset for ${pendingInitReset.full_name} (${pendingInitReset.email}).\n\nA one-time reset token will be generated. Continue?`
            : ''
        }
        confirmLabel="Continue"
        onConfirm={() => {
          if (pendingInitReset !== null) runInitiateReset(pendingInitReset)
        }}
      />
    </div>
  )
}
