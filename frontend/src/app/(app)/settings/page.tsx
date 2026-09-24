'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { SurfaceCard } from '@/components/ui/surface-card'
import { Input } from '@/components/ui/input'
import { Field } from '@/components/ui/field'
import { Banner } from '@/components/ui/banner'
import { ConfirmDialog } from '@/components/ui/dialog'
import { PageHeader } from '@/components/ui/page-header'
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

  const sectionHeading = 'text-lg font-semibold text-[#102A43]'

  return (
    <div className="min-h-screen">
      <main className="container mx-auto px-4 py-8">
        <div className="mx-auto max-w-4xl space-y-8">
          <PageHeader
            title="Settings"
            description="Your profile, planning calendar and the curriculum reference data SchemeKnit uses."
          />

          {error && <Banner tone="danger">{error}</Banner>}
          {success && <Banner tone="success">{success}</Banner>}

          {/* ── Account ─────────────────────────────────────────────── */}
          <section aria-labelledby="settings-account" className="space-y-6">
            <h2 id="settings-account" className={sectionHeading}>Account</h2>

            <SurfaceCard data-settings-profile accent="bg-gradient-to-r from-[#102A43] to-[#04A9CE]" className="px-5 py-5 sm:px-6">
              <div className="flex items-center">
                <User className="mr-2 h-5 w-5 text-[#04769B]" aria-hidden="true" />
                <div>
                  <h3 className="text-base font-semibold text-[#102A43]">Teacher Profile</h3>
                  <p className="text-sm text-muted-foreground">
                    Your name appears on the lesson plans you generate
                  </p>
                </div>
              </div>
              <div className="mt-4 space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <Field label="Full Name" htmlFor="profile-full-name">
                    <Input
                      id="profile-full-name"
                      type="text"
                      value={profileName}
                      onChange={(e) => setProfileName(e.target.value)}
                      placeholder="e.g. Ama Mensah"
                    />
                  </Field>
                  <Field label="Email" htmlFor="profile-email">
                    <Input
                      id="profile-email"
                      type="email"
                      value={profile?.email || ''}
                      disabled
                      className="bg-muted text-muted-foreground"
                    />
                  </Field>
                </div>
                <Field
                  label="School"
                  htmlFor="profile-school"
                  hint="Derived from your school membership and cannot be changed here"
                >
                  <Input
                    id="profile-school"
                    type="text"
                    value={profile?.school_name || '—'}
                    disabled
                    className="bg-muted text-muted-foreground"
                  />
                </Field>
                <Button onClick={handleSaveProfile} disabled={savingProfile || !profileName.trim()}>
                  <Save className="mr-2 h-4 w-4" />
                  {savingProfile ? 'Saving...' : 'Save Profile'}
                </Button>
              </div>
            </SurfaceCard>

            <ChangePasswordCard />
          </section>

          {/* ── Planning ────────────────────────────────────────────── */}
          <section aria-labelledby="settings-planning" className="space-y-4">
            <h2 id="settings-planning" className={sectionHeading}>Planning</h2>

            <SurfaceCard data-settings-holidays className="px-5 py-5 sm:px-6">
              <h3 className="text-base font-semibold text-[#102A43]">Holiday Calendar</h3>
              <p className="text-sm text-muted-foreground">
                Manage public holidays that affect lesson planning
              </p>

              <div className="mt-4 grid gap-4 md:grid-cols-4">
                <Field label="Holiday Name" htmlFor="holiday-name">
                  <Input
                    id="holiday-name"
                    type="text"
                    value={newHoliday.name}
                    onChange={(e) => setNewHoliday({ ...newHoliday, name: e.target.value })}
                    placeholder="e.g., Christmas Day"
                  />
                </Field>
                <Field label="Date" htmlFor="holiday-date">
                  <Input
                    id="holiday-date"
                    type="date"
                    value={newHoliday.date}
                    onChange={(e) => setNewHoliday({ ...newHoliday, date: e.target.value })}
                  />
                </Field>
                <div className="flex items-end pb-2">
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
                <div className="flex items-end pb-2">
                  <Button onClick={handleAddHoliday} disabled={saving}>
                    <Plus className="mr-2 h-4 w-4" />
                    Add
                  </Button>
                </div>
              </div>

              <div className="mt-4 space-y-2">
                {holidays.length === 0 ? (
                  <p className="py-4 text-center text-muted-foreground">No holidays configured</p>
                ) : (
                  holidays.map((holiday) => (
                    <div key={holiday.id} className="flex items-center justify-between rounded-lg bg-muted p-3">
                      <div>
                        <span className="font-medium">{holiday.name}</span>
                        <span className="ml-2 text-muted-foreground">
                          {new Date(holiday.date).toLocaleDateString()}
                        </span>
                        {holiday.is_recurring && (
                          <span className="ml-2 rounded bg-[#04A9CE]/10 px-2 py-1 text-xs text-[#04769B]">
                            Recurring
                          </span>
                        )}
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={`Delete holiday ${holiday.name}`}
                        onClick={() => setPendingDeleteId(holiday.id)}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                  ))
                )}
              </div>
            </SurfaceCard>
          </section>

          {/* ── Curriculum reference ────────────────────────────────── */}
          <section aria-labelledby="settings-reference" className="space-y-4">
            <h2 id="settings-reference" className={sectionHeading}>Curriculum reference</h2>

            <SurfaceCard data-settings-subjects className="px-5 py-5 sm:px-6">
              <h3 className="text-base font-semibold text-[#102A43]">Available Subjects</h3>
              <p className="text-sm text-muted-foreground">
                Subjects available per level. The list shown when you upload or
                generate follows the level you select.
              </p>
              <div className="mt-4 space-y-4">
                {subjectGroups.length > 0 ? (
                  subjectGroups.map((group) => (
                    <div key={group.class_level}>
                      <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                        {group.class_level}
                        <span className="ml-2 font-normal normal-case">
                          {group.educational_level}
                        </span>
                      </h4>
                      <div className="grid gap-2 md:grid-cols-3">
                        {group.subjects.map((subject) => (
                          <div key={`${group.class_level}-${subject}`} className="rounded bg-muted p-2 text-sm">
                            {subject}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="grid gap-2 md:grid-cols-3">
                    {subjects.map((subject) => (
                      <div key={subject} className="rounded bg-muted p-2 text-sm">{subject}</div>
                    ))}
                  </div>
                )}
              </div>
            </SurfaceCard>

            <SurfaceCard data-settings-levels className="px-5 py-5 sm:px-6">
              <h3 className="text-base font-semibold text-[#102A43]">Available Class Levels</h3>
              <p className="text-sm text-muted-foreground">Class levels supported by SchemeKnit</p>
              <div className="mt-4 grid gap-2 md:grid-cols-3">
                {classLevels.map((level) => (
                  <div key={level} className="rounded bg-muted p-2 text-sm">{level}</div>
                ))}
              </div>
            </SurfaceCard>
          </section>

          {/* ── About ───────────────────────────────────────────────── */}
          <section aria-labelledby="settings-about" className="space-y-4">
            <h2 id="settings-about" className={sectionHeading}>About</h2>

            <SurfaceCard data-settings-about className="px-5 py-5 sm:px-6">
              <div className="space-y-2 text-sm text-muted-foreground">
                <p><strong className="text-[#102A43]">Version:</strong> 1.0.5</p>
                <p><strong className="text-[#102A43]">Developer:</strong> BloomCore Technologies</p>
                <p>
                  SchemeKnit is a professional lesson plan generator designed for
                  Ghanaian teachers. It extracts curriculum data from scheme of work
                  documents and generates formatted lesson plans aligned with
                  Ghana Education Service standards.
                </p>
                <p>
                  <Link href="/dashboard" className="font-medium text-[#04769B] hover:underline">
                    Back to Dashboard
                  </Link>
                </p>
              </div>
            </SurfaceCard>
          </section>

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
