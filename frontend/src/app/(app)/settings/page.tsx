'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Banner } from '@/components/ui/banner'
import { ConfirmDialog } from '@/components/ui/dialog'
import { Save, Plus, Trash2, User } from 'lucide-react'
import { api } from '@/lib/api'
import { ChangePasswordCard } from '@/components/change-password'
import { Holiday } from '@/types'

export default function SettingsPage() {
  const [holidays, setHolidays] = useState<Holiday[]>([])
  const [subjects, setSubjects] = useState<string[]>([])
  const [subjectGroups, setSubjectGroups] = useState<{ class_level: string; educational_level: string; subjects: string[] }[]>([])
  const [classLevels, setClassLevels] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [newHoliday, setNewHoliday] = useState({ name: '', date: '', is_recurring: false })
  const [profile, setProfile] = useState<{ email?: string; full_name?: string; school_name?: string } | null>(null)
  const [profileName, setProfileName] = useState('')
  const [savingProfile, setSavingProfile] = useState(false)
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null)

  useEffect(() => {
    loadSettings()
  }, [])

  const loadSettings = async () => {
    try {
      setLoading(true)
      const [holidaysData, subjectsData, classLevelsData, profileData, groupsData] = await Promise.all([
        api.listHolidays(),
        api.listSubjects(),
        api.listClassLevels(),
        api.getProfile().catch(() => null),
        api.listSubjectsByLevel().catch(() => ({ levels: [] })),
      ])
      setHolidays(holidaysData.holidays || [])
      setSubjects(subjectsData.subjects || [])
      setSubjectGroups(groupsData.levels || [])
      setClassLevels(classLevelsData.class_levels || [])
      if (profileData) {
        setProfile(profileData)
        setProfileName(profileData.full_name || '')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load settings')
    } finally {
      setLoading(false)
    }
  }

  const handleSaveProfile = async () => {
    try {
      setSavingProfile(true)
      setError(null)
      const updated = await api.updateProfile({ full_name: profileName.trim() })
      setProfile(updated)
      setSuccess('Profile updated successfully')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update profile')
    } finally {
      setSavingProfile(false)
    }
  }

  const handleAddHoliday = async () => {
    if (!newHoliday.name || !newHoliday.date) {
      setError('Please fill in all fields')
      return
    }
    try {
      setSaving(true)
      setError(null)
      await api.addHoliday({
        name: newHoliday.name,
        date: newHoliday.date,
        is_recurring: newHoliday.is_recurring
      })
      setNewHoliday({ name: '', date: '', is_recurring: false })
      setSuccess('Holiday added successfully')
      const holidaysData = await api.listHolidays()
      setHolidays(holidaysData.holidays || [])
      setTimeout(() => setSuccess(null), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add holiday')
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteHoliday = async (holidayId: string) => {
    try {
      await api.deleteHoliday(holidayId)
      setHolidays(holidays.filter(h => h.id !== holidayId))
      setSuccess('Holiday deleted successfully')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete holiday')
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto"></div>
          <p className="mt-4 text-muted-foreground">Loading settings...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen">
      <main className="container mx-auto px-4 py-8">
        <div className="max-w-4xl mx-auto space-y-6">
          {error && <Banner tone="danger">{error}</Banner>}
          {success && <Banner tone="success">{success}</Banner>}

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center">
                <User className="h-5 w-5 mr-2" />
                Teacher Profile
              </CardTitle>
              <CardDescription>
                Your name appears on the lesson plans you generate
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Full Name</label>
                  <Input
                    type="text"
                    value={profileName}
                    onChange={(e) => setProfileName(e.target.value)}
                    placeholder="e.g. Ama Mensah"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Email</label>
                  <Input
                    type="email"
                    value={profile?.email || ''}
                    disabled
                    className="bg-muted text-muted-foreground"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">School</label>
                <Input
                  type="text"
                  value={profile?.school_name || '—'}
                  disabled
                  className="bg-muted text-muted-foreground"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Derived from your school membership and cannot be changed here
                </p>
              </div>
              <Button onClick={handleSaveProfile} disabled={savingProfile || !profileName.trim()}>
                <Save className="h-4 w-4 mr-2" />
                {savingProfile ? 'Saving...' : 'Save Profile'}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Holiday Calendar</CardTitle>
              <CardDescription>
                Manage public holidays that affect lesson planning
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid md:grid-cols-4 gap-4 mb-6">
                <div>
                  <label className="block text-sm font-medium mb-2">Holiday Name</label>
                  <Input
                    type="text"
                    value={newHoliday.name}
                    onChange={(e) => setNewHoliday({ ...newHoliday, name: e.target.value })}
                    placeholder="e.g., Christmas Day"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-2">Date</label>
                  <Input
                    type="date"
                    value={newHoliday.date}
                    onChange={(e) => setNewHoliday({ ...newHoliday, date: e.target.value })}
                  />
                </div>
                <div className="flex items-end">
                  <label className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      checked={newHoliday.is_recurring}
                      onChange={(e) => setNewHoliday({ ...newHoliday, is_recurring: e.target.checked })}
                      className="rounded"
                    />
                    <span className="text-sm">Recurring annually</span>
                  </label>
                </div>
                <div className="flex items-end">
                  <Button onClick={handleAddHoliday} disabled={saving}>
                    <Plus className="h-4 w-4 mr-2" />
                    Add
                  </Button>
                </div>
              </div>

              <div className="space-y-2">
                {holidays.length === 0 ? (
                  <p className="text-muted-foreground text-center py-4">No holidays configured</p>
                ) : (
                  holidays.map((holiday) => (
                    <div key={holiday.id} className="flex items-center justify-between p-3 bg-muted rounded-lg">
                      <div>
                        <span className="font-medium">{holiday.name}</span>
                        <span className="text-muted-foreground ml-2">
                          {new Date(holiday.date).toLocaleDateString()}
                        </span>
                        {holiday.is_recurring && (
                          <span className="text-xs bg-primary/10 text-primary px-2 py-1 rounded ml-2">Recurring</span>
                        )}
                      </div>
                      <Button variant="ghost" size="sm" onClick={() => setPendingDeleteId(holiday.id)}>
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  ))
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Available Subjects</CardTitle>
              <CardDescription>
                Subjects available per level. The list shown when you upload or
                generate follows the level you select.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {subjectGroups.length > 0 ? (
                subjectGroups.map((group) => (
                  <div key={group.class_level}>
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
                      {group.class_level}
                      <span className="ml-2 font-normal normal-case">
                        {group.educational_level}
                      </span>
                    </h4>
                    <div className="grid md:grid-cols-3 gap-2">
                      {group.subjects.map((subject) => (
                        <div key={`${group.class_level}-${subject}`} className="p-2 bg-muted rounded text-sm">
                          {subject}
                        </div>
                      ))}
                    </div>
                  </div>
                ))
              ) : (
                <div className="grid md:grid-cols-3 gap-2">
                  {subjects.map((subject) => (
                    <div key={subject} className="p-2 bg-muted rounded text-sm">{subject}</div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Available Class Levels</CardTitle>
              <CardDescription>Class levels supported by SchemeKnit</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid md:grid-cols-3 gap-2">
                {classLevels.map((level) => (
                  <div key={level} className="p-2 bg-muted rounded text-sm">{level}</div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>About SchemeKnit</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 text-sm text-muted-foreground">
                <p><strong>Version:</strong> 1.0.5</p>
                <p><strong>Developer:</strong> BloomCore Technologies</p>
                <p>
                  SchemeKnit is a professional lesson plan generator designed for
                  Ghanaian teachers. It extracts curriculum data from scheme of work
                  documents and generates formatted lesson plans aligned with
                  Ghana Education Service standards.
                </p>
              </div>
            </CardContent>
          </Card>

          <ChangePasswordCard />

          <ConfirmDialog
            open={pendingDeleteId !== null}
            onOpenChange={(open) => {
              if (!open) setPendingDeleteId(null)
            }}
            title="Delete holiday"
            message="Are you sure you want to delete this holiday?"
            confirmLabel="Delete"
            destructive
            onConfirm={() => {
              if (pendingDeleteId !== null) handleDeleteHoliday(pendingDeleteId)
            }}
          />
        </div>
      </main>
    </div>
  )
}
