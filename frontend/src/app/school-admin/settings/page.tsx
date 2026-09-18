'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { api } from '@/lib/api'
import { ChangePasswordCard } from '@/components/change-password'

export default function SchoolSettingsPage() {
  const [form, setForm] = useState({ name: '', contact_name: '', contact_phone: '', contact_email: '', address: '' })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    load()
  }, [])

  const load = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await api.getMySchool()
      const s = data.school || {}
      setForm({
        name: s.name || '',
        contact_name: s.contact_name || '',
        contact_phone: s.contact_phone || '',
        contact_email: s.contact_email || '',
        address: s.address || '',
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load settings')
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    if (!form.name.trim()) {
      setError('School name is required')
      return
    }
    try {
      setSaving(true)
      setError(null)
      setSaved(false)
      await api.updateMySchool(form)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    )
  }

  return (
    <div className="max-w-2xl space-y-4">
      <h1 className="text-2xl font-bold">School Settings</h1>
      {error && (
        <div className="p-4 bg-destructive/10 border border-destructive/20 rounded-lg">
          <p className="text-destructive text-sm">{error}</p>
        </div>
      )}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">School Profile</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">School Name</label>
            <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-full px-3 py-2 border rounded-md" />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Contact Name</label>
            <input type="text" value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })}
              className="w-full px-3 py-2 border rounded-md" />
          </div>
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1">Contact Phone</label>
              <input type="text" value={form.contact_phone} onChange={(e) => setForm({ ...form, contact_phone: e.target.value })}
                className="w-full px-3 py-2 border rounded-md" />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Contact Email</label>
              <input type="email" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })}
                className="w-full px-3 py-2 border rounded-md" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Address</label>
            <textarea value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })}
              rows={3} className="w-full px-3 py-2 border rounded-md" />
          </div>
          <div className="flex items-center gap-3">
            <Button onClick={handleSave} disabled={saving}>
              {saving ? 'Saving...' : 'Save Changes'}
            </Button>
            {saved && <span className="text-sm text-green-600">Saved</span>}
          </div>
          <p className="text-xs text-muted-foreground">
            Plan, seat limit, and license dates are managed by SchemeKnit.
            Contact support to change your subscription.
          </p>
        </CardContent>
      </Card>

      <ChangePasswordCard />
    </div>
  )
}
