// SchemeKnit API Service

import { DEV_TOOLS_ENABLED } from './dev-tools'
import type {
  WapefOptions,
  WeeklyClassPlan,
  WeeklyDayOption,
  WeeklyPlanListItem,
  WeeklyPlanRequest,
  WeeklyPreviewResponse,
  WeeklyRouting,
} from '@/types'

/**
 * Single source of truth for the API base URL.
 *
 * - Electron (desktop): local bundled backend at 127.0.0.1:18234
 * - Web production: NEXT_PUBLIC_API_URL (e.g. https://schemeknit-api.onrender.com)
 * - Local dev fallback: http://localhost:8000
 *
 * Exported so the service-status health check and any other client-side
 * code that needs the backend origin can reuse this without duplicating
 * the Electron / env-var logic.
 */
export function getApiBaseUrl(): string {
  if (typeof window !== 'undefined' && (window as any).electronAPI) {
    return 'http://127.0.0.1:18234'
  }
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
}

const API_BASE_URL = getApiBaseUrl()

class ApiService {
  private baseUrl: string
  private authToken: string | null = null

  constructor() {
    this.baseUrl = API_BASE_URL
  }

  get isElectron(): boolean {
    return typeof window !== 'undefined' && !!(window as any).electronAPI
  }

  setToken(token: string | null) {
    this.authToken = token
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`
    
    const defaultHeaders: Record<string, string> = {
      'Content-Type': 'application/json',
    }

    if (this.authToken) {
      defaultHeaders['Authorization'] = `Bearer ${this.authToken}`
    }

    const response = await fetch(url, {
      ...options,
      headers: {
        ...defaultHeaders,
        ...options.headers,
      },
    })

    if (!response.ok) {
      // Expired/invalid sessions: drop the stale token and return to login
      // instead of stranding the user on error banners. 403 (forbidden but
      // authenticated, e.g. role boundaries) must NOT log out.
      if (response.status === 401 && typeof window !== 'undefined'
          && !endpoint.startsWith('/api/auth/login')
          && !endpoint.startsWith('/api/auth/setup')) {
        this.authToken = null
        try {
          // Clear ONLY this tab's session (sessionStorage is tab-scoped), so an
          // expired/invalid session logs out just this tab, never other tabs.
          sessionStorage.removeItem('teachflow_token')
          sessionStorage.removeItem('teachflow_user')
          if (!window.location.pathname.startsWith('/login')) {
            window.location.href = '/login'
          }
        } catch {
          // storage may be unavailable; the error below still surfaces
        }
      }
      const error = await response.json().catch(() => ({
        detail: 'An error occurred'
      }))
      throw errorFromDetail(error?.detail)
    }

    return response.json()
  }

  // Auth API
  async login(email: string, password: string): Promise<any> {
    return this.request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
  }

  async getSetupStatus(): Promise<{ needs_setup: boolean; user_count: number }> {
    return this.request('/api/auth/setup/status')
  }

  async firstRunSetup(data: { name: string; email: string; password: string; school_name?: string }): Promise<any> {
    return this.request('/api/auth/setup', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async register(email: string, password: string, fullName: string, schoolName?: string): Promise<any> {
    return this.request('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name: fullName, school_name: schoolName || '' }),
    })
  }

  async registerIndividual(email: string, password: string, fullName: string): Promise<any> {
    return this.request('/api/auth/register/individual', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name: fullName }),
    })
  }

  async getMyPlan(): Promise<any> {
    return this.request('/api/auth/my-plan')
  }

  async listIndividualTeachers(): Promise<{ teachers: any[]; count: number }> {
    return this.request('/api/platform-admin/individual-teachers')
  }

  async getIndividualTeacher(teacherId: string): Promise<any> {
    return this.request(`/api/platform-admin/individual-teachers/${teacherId}`)
  }

  async activateIndividualTeacher(teacherId: string, productPlanId: string, durationDays?: number): Promise<any> {
    return this.request('/api/platform-admin/individual-teachers/activate', {
      method: 'POST',
      body: JSON.stringify({ teacher_id: teacherId, product_plan_id: productPlanId, duration_days: durationDays }),
    })
  }

  async revokeIndividualTeacher(teacherId: string, reason = ''): Promise<any> {
    return this.request(`/api/platform-admin/individual-teachers/${teacherId}/revoke`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    })
  }

  async extendIndividualTeacher(teacherId: string, durationDays: number): Promise<any> {
    return this.request(`/api/platform-admin/individual-teachers/${teacherId}/extend`, {
      method: 'POST',
      body: JSON.stringify({ duration_days: durationDays }),
    })
  }

  async activateIndividualLicense(activationCode: string): Promise<any> {
    return this.request('/api/auth/activate-individual', {
      method: 'POST',
      body: JSON.stringify({ activation_code: activationCode }),
    })
  }

  async createIndividualActivationCode(teacherEmail: string, productPlanId: string): Promise<any> {
    return this.request('/api/platform-admin/activation-codes', {
      method: 'POST',
      body: JSON.stringify({ teacher_email: teacherEmail, product_plan_id: productPlanId }),
    })
  }

  async listIndividualActivationCodes(): Promise<{ codes: any[]; count: number }> {
    return this.request('/api/platform-admin/activation-codes')
  }

  async getMaintenanceMode(): Promise<{ maintenance: { active: boolean; message: string; estimated_restore: string } }> {
    return this.request('/api/platform-admin/maintenance')
  }

  async setMaintenanceMode(enabled: boolean, message?: string, estimatedRestore?: string): Promise<any> {
    return this.request('/api/platform-admin/maintenance', {
      method: 'POST',
      body: JSON.stringify({ enabled, message: message || '', estimated_restore: estimatedRestore || '' }),
    })
  }

  async getServiceStatus(): Promise<{ status: string; maintenance: { active: boolean; message: string; estimated_restore: string }; version: string }> {
    return this.request('/api/service-status')
  }

  async listUsers(): Promise<{ users: any[] }> {
    return this.request('/api/auth/users')
  }

  async createTeacher(data: { email: string; password: string; full_name: string; school_name?: string }): Promise<any> {
    return this.request('/api/auth/users', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async toggleUserActive(userId: string): Promise<any> {
    return this.request(`/api/auth/users/${userId}/toggle-active`, {
      method: 'PUT',
    })
  }

  async resetUserPassword(userId: string, password: string): Promise<any> {
    return this.request(`/api/auth/users/${userId}/reset-password`, {
      method: 'POST',
      body: JSON.stringify({ email: '', password }),
    })
  }

  // ── Platform Admin Bootstrap ──────────────────────────────────────────────

  async getPlatformAdminSetupStatus(): Promise<{ bootstrap_required: boolean }> {
    return this.request('/api/auth/setup-platform-admin/status')
  }

  async setupPlatformAdmin(data: {
    bootstrap_secret: string
    full_name: string
    email: string
    password: string
  }): Promise<{ access_token: string; user: any }> {
    return this.request('/api/auth/setup-platform-admin', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  // ── Self-service password change ──────────────────────────────────────────

  async changePassword(
    currentPassword: string,
    newPassword: string,
  ): Promise<{ access_token: string; message: string }> {
    return this.request('/api/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    })
  }

  // ── Admin-initiated token-based reset ─────────────────────────────────────

  async initiatePasswordReset(userId: string): Promise<{
    reset_token: string
    expires_in_minutes: number
    target_email: string
    message: string
  }> {
    return this.request(`/api/auth/users/${userId}/initiate-reset`, {
      method: 'POST',
    })
  }

  async validateResetToken(token: string): Promise<{ email: string; full_name: string }> {
    const params = new URLSearchParams({ token })
    return this.request(`/api/auth/reset-token/validate?${params.toString()}`)
  }

  async confirmPasswordReset(token: string, newPassword: string): Promise<{ message: string }> {
    return this.request('/api/auth/confirm-password-reset', {
      method: 'POST',
      body: JSON.stringify({ reset_token: token, new_password: newPassword }),
    })
  }

  async getProfile(): Promise<any> {
    return this.request('/api/auth/me')
  }

  async updateProfile(data: { full_name?: string; school_name?: string }): Promise<any> {
    return this.request('/api/auth/me', {
      method: 'PUT',
      body: JSON.stringify(data),
    })
  }

  // Documents API
  async uploadScheme(file: File) {
    const formData = new FormData()
    formData.append('file', file)

    const headers: Record<string, string> = {}
    if (this.authToken) {
      headers['Authorization'] = `Bearer ${this.authToken}`
    }

    const response = await fetch(`${this.baseUrl}/api/documents/upload`, {
      method: 'POST',
      body: formData,
      headers,
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        detail: 'Upload failed'
      }))
      throw new Error(error.detail || 'Upload failed')
    }

    return response.json()
  }

  // ── Multi-subject document detection (§4) ────────────────────────────
  async getDocumentDetection(schemeId: string): Promise<any> {
    return this.request(`/api/documents/${schemeId}/detection`)
  }

  async confirmSubjectSection(schemeId: string, subject: string): Promise<any> {
    return this.request(`/api/documents/${schemeId}/confirm-subject`, {
      method: 'POST',
      body: JSON.stringify({ subject }),
    })
  }




  async getScheme(schemeId: string): Promise<any> {
    return this.request(`/api/documents/${schemeId}`)
  }

  /**
   * ``source_provides_indicators`` distinguishes "the parser could not read an
   * indicator this week" from "the source has no Indicator column at all"
   * (real-use remediation, Defect 2) — the review UI must never conflate them.
   */
  async getSchemeWeeks(schemeId: string): Promise<{ weeks: any[]; source_provides_indicators?: boolean }> {
    return this.request(`/api/documents/${schemeId}/weeks`)
  }

  async getSchemeWorkflow(schemeId: string): Promise<{
    scheme_id: string
    scheme_status: string
    stages: { key: string; state: 'completed' | 'active' | 'locked' }[]
    lesson_count: number
    exported: boolean
  }> {
    return this.request(`/api/documents/${schemeId}/workflow`)
  }

  async updateSchemeStatus(schemeId: string, status: string) {
    return this.request(`/api/documents/${schemeId}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    })
  }

  async deleteScheme(schemeId: string) {
    return this.request(`/api/documents/${schemeId}`, {
      method: 'DELETE',
    })
  }

  async listSchemes(): Promise<{ schemes: any[] }> {
    return this.request('/api/documents/')
  }

  // Curriculum API
  async validateScheme(schemeId: string): Promise<any> {
    return this.request(`/api/curriculum/${schemeId}/validate`)
  }

  async allocateCurriculum(schemeId: string, config: any): Promise<any> {
    return this.request(`/api/curriculum/${schemeId}/allocate`, {
      method: 'POST',
      body: JSON.stringify(config),
    })
  }

  async approveScheme(schemeId: string): Promise<any> {
    return this.request(`/api/curriculum/${schemeId}/approve`, {
      method: 'POST',
    })
  }

  async getSchemeSummary(schemeId: string): Promise<any> {
    return this.request(`/api/curriculum/${schemeId}/summary`)
  }

  // Free Tier lesson-plan quota for the current calendar month (server-derived).
  async getLessonQuota(): Promise<any> {
    return this.request('/api/generation/quota')
  }

  // Allocation preview
  async getAllocationPreview(schemeId: string, config: any): Promise<any> {
    return this.request(`/api/generation/${schemeId}/allocation-preview`, {
      method: 'POST',
      body: JSON.stringify(sanitizeTermConfig(config)),
    })
  }

  // Per-lesson review drafts (saved BEFORE generation)
  async getLessonReview(schemeId: string): Promise<{ drafts: Record<string, any> }> {
    return this.request(`/api/generation/${schemeId}/lesson-review`)
  }

  async saveLessonReview(schemeId: string, drafts: Record<string, any>): Promise<{ drafts: Record<string, any> }> {
    return this.request(`/api/generation/${schemeId}/lesson-review`, {
      method: 'PUT',
      body: JSON.stringify({ drafts }),
    })
  }

  // Approved WAPEF Plan option lists (teacher-selected structured fields)
  async getWapefOptions(): Promise<WapefOptions> {
    return this.request('/api/generation/wapef/options')
  }

  // Generation API
  async generateLessonPlans(schemeId: string, config: any): Promise<any> {
    return this.request(`/api/generation/${schemeId}/generate`, {
      method: 'POST',
      body: JSON.stringify(sanitizeTermConfig(config)),
    })
  }

  async listAllLessons(): Promise<{ lesson_plans: any[]; total: number }> {
    return this.request('/api/generation/lessons')
  }

  async getGenerationStatus(jobId: string): Promise<any> {
    return this.request(`/api/generation/${jobId}/status`)
  }

  async getGenerationStatusForScheme(schemeId: string): Promise<any> {
    return this.request(`/api/generation/scheme/${schemeId}/status`)
  }

  async getGeneratedLessons(jobId: string): Promise<any> {
    return this.request(`/api/generation/${jobId}/lessons`)
  }

  async getLessonPlan(jobId: string, lessonIndex: number): Promise<any> {
    return this.request(`/api/generation/${jobId}/lessons/${lessonIndex}`)
  }

  async getLesson(lessonId: string): Promise<any> {
    return this.request(`/api/generation/lessons/${lessonId}`)
  }

  async regenerateSection(lessonId: string, section: string, aiMode = 'ollama', context = '', requestId = ''): Promise<{
    section: string
    previous_content: string
    new_content: string
    /** Structured activities, present for section "main_activities". */
    new_activities?: { phase?: string; description: string; duration_minutes?: number | null; resources?: string[] }[] | null
    provider: string
    model: string
    mode: string
    timestamp: string
    source: string
  }> {
    return this.request('/api/ai/regenerate-section', {
      method: 'POST',
      body: JSON.stringify({
        lesson_plan_id: lessonId,
        section,
        ai_mode: aiMode,
        additional_context: context,
        // Idempotency key: a duplicate submission for the same successful
        // generation must not consume a second AI allowance.
        request_id: requestId || undefined,
      }),
    })
  }

  async updateLesson(lessonId: string, updates: any): Promise<any> {
    return this.request(`/api/generation/lessons/${lessonId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    })
  }

  async updateLessonPlan(jobId: string, lessonIndex: number, updates: any): Promise<any> {
    return this.request(`/api/generation/${jobId}/lessons/${lessonIndex}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    })
  }

  async getCurriculumCoverage(jobId: string): Promise<any> {
    return this.request(`/api/generation/${jobId}/coverage`)
  }

  // Headers for raw fetch() calls (blob downloads). The backend's HTTPBearer
  // returns 403 when the Authorization header is absent, so exports must send it.
  private authHeaders(): Record<string, string> {
    return this.authToken ? { Authorization: `Bearer ${this.authToken}` } : {}
  }

  /**
   * Map an export HTTP failure to a truthful, user-facing message (PART 22).
   * The backend detail wins when present (it names the real limitation, e.g.
   * LibreOffice availability for PDF); the status refines the generic cases.
   */
  private exportErrorMessage(status: number, detail: string | null): string {
    // PART D: truthful, useful, non-technical messages. The backend's own
    // detail wins when present because it names the real limitation; these
    // branches cover the classes the backend cannot phrase for the teacher.
    if (status === 401) {
      return detail || 'Your session has expired. Please sign in again and retry the download.'
    }
    if (status === 403) {
      return detail || 'You do not have permission to download this plan.'
    }
    if (status === 404) {
      // The one-time link expired/was already used, or the file is gone.
      return detail || 'This download link is no longer valid. Please start the download again.'
    }
    if (status === 429) {
      return detail || 'Too many download requests. Please wait a moment and try again.'
    }
    if (status === 503) {
      return detail || 'Export failed — the download service is temporarily unavailable. Please try again shortly.'
    }
    if (detail) return detail
    if (status >= 500) {
      return 'Export failed — the download service is temporarily unavailable. Please try again shortly.'
    }
    return `Export failed (${status})`
  }

  private async exportBlob(url: string): Promise<ExportPayload> {
    let response: Response
    try {
      response = await fetch(url, { method: 'POST', headers: this.authHeaders() })
    } catch (err) {
      // PART D: distinguish a genuine network failure from an HTTP error so the
      // teacher never sees a bare "Failed to fetch". The real cause is logged
      // for diagnostics and never rendered.
      if (typeof console !== 'undefined') console.error('[download] network failure', url, err)
      throw new Error('We could not complete the download. Please check your connection and try again.')
    }
    if (!response.ok) {
      // PART 22: surface the ACTUAL cause — auth expiry, permissions, server
      // export failure, environment limitation — never a bare "Failed to fetch".
      const err = await response.json().catch(() => ({} as any))
      throw new Error(this.exportErrorMessage(response.status, err?.detail ?? null))
    }
    const blob = await response.blob()
    // The server names the file. It sends the name in a custom header because a
    // `Content-Disposition: attachment` response is classified by Chrome/Edge as
    // a download and refused by fetch() for some content types (notably
    // application/zip), which silently broke ZIP export. Fall back to the
    // disposition header for older/other servers.
    const encoded = response.headers.get('X-TeachFlow-Filename')
    let filename: string | null = null
    if (encoded) {
      try {
        filename = decodeURIComponent(encoded)
      } catch {
        filename = encoded
      }
    }
    return {
      blob,
      filename: filename || filenameFromContentDisposition(response.headers.get('Content-Disposition')),
    }
  }

  async exportDocx(jobId: string, templateType: string = 'GES-style', templateId?: string) {
    const params = new URLSearchParams({ template_type: templateType })
    if (templateId) params.append('template_id', templateId)
    return this.exportBlob(`${this.baseUrl}/api/generation/${jobId}/export/docx?${params}`)
  }

  async exportPdf(jobId: string, templateType: string = 'GES-style', templateId?: string) {
    const params = new URLSearchParams({ template_type: templateType })
    if (templateId) params.append('template_id', templateId)
    return this.exportBlob(`${this.baseUrl}/api/generation/${jobId}/export/pdf?${params}`)
  }

  /**
   * One-time authenticated download URL for an export (PART 27).
   *
   * The POST renders and validates here — a genuine failure (no converter,
   * failed conversion, missing job) surfaces as a real error on this request.
   * On success it returns a single-use URL the browser navigates to directly,
   * so the browser or a download manager (IDM) owns the transfer end to end.
   * There is no fetch() body read on the page to race against, so a successful
   * handoff can no longer be misreported as "Failed to fetch".
   */
  async getDownloadUrl(jobId: string, format: string,
                       templateType: string = 'GES-style',
                       templateId?: string): Promise<{ download_url: string; filename: string; media_type: string }> {
    const params = new URLSearchParams({ format, template_type: templateType })
    if (templateId) params.append('template_id', templateId)
    try {
      return await this.request(`/api/generation/${jobId}/download-url?${params}`, { method: 'POST' })
    } catch (err) {
      // PART T: a browser-level fetch rejection (offline, DNS, CORS, mixed
      // content) surfaces as TypeError("Failed to fetch"). Translate it to a
      // truthful message instead of letting the raw text reach the teacher.
      if (err instanceof TypeError) {
        if (typeof console !== 'undefined') console.error('[download-url] network failure', err)
        throw new Error('We could not complete the download. Please check your connection and try again.')
      }
      throw err
    }
  }

  /**
   * Navigate to a one-time download URL so the browser/IDM handles the save.
   * Uses a form POST in a hidden iframe-free way: a simple anchor navigation
   * keeps the current page alive (the response is a download, not a document).
   */
  navigateToDownload(downloadUrl: string): void {
    // A real navigation to an attachment response saves the file without
    // replacing the page. Using window.location would still work, but an
    // anchor click keeps browser history clean and matches the Electron path.
    //
    // The server issues a root-relative URL. In the split-origin web build the
    // app is served from a different host/port than the API (e.g. :3000 vs
    // :8000), so a bare relative href would navigate the page to the frontend
    // origin and hit a 404 instead of the download. Resolve it against the API
    // base so the browser reaches the real endpoint.
    const href = /^(https?:)?\/\//i.test(downloadUrl)
      ? downloadUrl
      : `${this.baseUrl}${downloadUrl}`
    const a = document.createElement('a')
    a.href = href
    a.rel = 'noopener'
    a.style.display = 'none'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  async exportXlsx(jobId: string) {
    return this.exportBlob(`${this.baseUrl}/api/generation/${jobId}/export/xlsx`)
  }

  async exportZip(jobId: string, templateType: string = 'GES-style', templateId?: string) {
    const params = new URLSearchParams({ template_type: templateType })
    // Without this the ZIP silently fell back to the built-in template while the
    // DOCX honoured the selection, so the same export produced two layouts.
    if (templateId) params.append('template_id', templateId)
    return this.exportBlob(`${this.baseUrl}/api/generation/${jobId}/export/zip?${params}`)
  }

  // Templates API
  // classLevel matters as well as educationalLevel: the GES primary form covers
  // Basic 1-3 only, so the default differs inside one educational level.
  async listTemplates(educationalLevel?: string, classLevel?: string): Promise<{ templates: any[] }> {
    const params = new URLSearchParams()
    if (educationalLevel) params.append('educational_level', educationalLevel)
    if (classLevel) params.append('class_level', classLevel)
    const query = params.toString()
    return this.request(`/api/templates/${query ? `?${query}` : ''}`)
  }

  async getTemplate(templateId: string): Promise<any> {
    return this.request(`/api/templates/${templateId}`)
  }

  // Custom sample-template flow: analyze -> review mappings -> save
  async analyzeTemplateSample(file: File): Promise<any> {
    const formData = new FormData()
    formData.append('file', file)

    const headers: Record<string, string> = {}
    if (this.authToken) {
      headers['Authorization'] = `Bearer ${this.authToken}`
    }

    const response = await fetch(`${this.baseUrl}/api/templates/analyze`, {
      method: 'POST',
      body: formData,
      headers,
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({
        detail: 'Sample analysis failed'
      }))
      throw new Error(error.detail || 'Sample analysis failed')
    }
    return response.json()
  }

  async saveCustomTemplate(payload: any): Promise<any> {
    return this.request('/api/templates/save', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  }

  async getCustomTemplate(templateId: string): Promise<any> {
    return this.request(`/api/templates/custom/${templateId}`)
  }

  async previewCustomTemplate(templateId: string): Promise<any> {
    return this.request(`/api/templates/custom/${templateId}/preview`)
  }

  async updateCustomTemplate(templateId: string, payload: any): Promise<any> {
    return this.request(`/api/templates/${templateId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
  }

  async versionCustomTemplate(templateId: string, version: string): Promise<any> {
    return this.request(`/api/templates/${templateId}/version`, {
      method: 'POST',
      body: JSON.stringify({ version }),
    })
  }

  async archiveCustomTemplate(templateId: string): Promise<any> {
    return this.request(`/api/templates/${templateId}/archive`, {
      method: 'POST',
    })
  }

  async deleteCustomTemplate(templateId: string): Promise<any> {
    return this.request(`/api/templates/${templateId}`, {
      method: 'DELETE',
    })
  }

  async listProfiles(): Promise<{ profiles: any[] }> {
    return this.request('/api/templates/profiles')
  }

  // Settings API
  async listHolidays(): Promise<{ holidays: any[] }> {
    return this.request('/api/settings/holidays')
  }

  async addHoliday(holiday: any): Promise<any> {
    return this.request('/api/settings/holidays', {
      method: 'POST',
      body: JSON.stringify(holiday),
    })
  }

  async deleteHoliday(holidayId: string): Promise<any> {
    return this.request(`/api/settings/holidays/${holidayId}`, {
      method: 'DELETE',
    })
  }

  async listSubjects(level?: string): Promise<{ subjects: string[]; level?: string | null }> {
    const qs = level ? `?level=${encodeURIComponent(level)}` : ''
    return this.request(`/api/settings/subjects${qs}`)
  }

  async listSubjectsByLevel(): Promise<{ levels: { class_level: string; educational_level: string; subjects: string[] }[] }> {
    return this.request('/api/settings/subjects/by-level')
  }

  async listClassLevels(): Promise<{ class_levels: string[] }> {
    return this.request('/api/settings/class-levels')
  }

  async listTemplateTypes(): Promise<{ template_types: any[] }> {
    return this.request('/api/settings/template-types')
  }

  async listAIModes(): Promise<{ ai_modes: any[] }> {
    return this.request('/api/settings/ai-modes')
  }

  /** Actual AI mode/provider resolution for a requested mode (secret-free). */
  async getAiStatus(aiMode: string): Promise<{
    mode: string; active: boolean; provider: string | null;
    provider_key: string | null; state: string; reason: string | null;
  }> {
    return this.request(`/api/settings/ai-status?ai_mode=${encodeURIComponent(aiMode)}`)
  }

  async listTeachingDays(): Promise<{ teaching_days: any[] }> {
    return this.request('/api/settings/teaching-days')
  }

  // Payment API
  async getPaymentConfig(): Promise<any> {
    return this.request('/api/payments/config')
  }

  async submitPayment(data: {
    payment_method: string
    amount: number
    product_type: string
    product_id: string
    product_name: string
    reference: string
    payer_name: string
    payer_phone: string
    notes: string
  }): Promise<any> {
    return this.request('/api/payments/submit', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async getPaymentHistory(): Promise<{ payments: any[] }> {
    return this.request('/api/payments/history')
  }

  async listProductPlans(): Promise<{ plans: any[] }> {
    return this.request('/api/payments/plans')
  }

  // Admin API
  async getAdminPendingPayments(): Promise<{ payments: any[] }> {
    return this.request('/api/payments/admin/pending')
  }

  async getAdminAllPayments(status?: string): Promise<{ payments: any[] }> {
    const params = status ? `?status=${status}` : ''
    return this.request(`/api/payments/admin/all${params}`)
  }

  async adminVerifyPayment(paymentId: string, notes?: string): Promise<any> {
    return this.request(`/api/payments/admin/${paymentId}/verify`, {
      method: 'POST',
      body: JSON.stringify({ notes: notes || '' }),
    })
  }

  async adminRejectPayment(paymentId: string, reason: string): Promise<any> {
    return this.request(`/api/payments/admin/${paymentId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ rejection_reason: reason }),
    })
  }

  async getAdminRevenueStats(): Promise<any> {
    return this.request('/api/payments/admin/revenue')
  }

  async getAdminAuditLogs(paymentId?: string): Promise<{ logs: any[] }> {
    const params = paymentId ? `?payment_id=${paymentId}` : ''
    return this.request(`/api/payments/admin/audit${params}`)
  }

  // School Admin (school-scoped) API
  async getMySchool(): Promise<any> {
    return this.request('/api/auth/my-school')
  }

  async updateMySchool(data: { name?: string; contact_name?: string; contact_phone?: string; contact_email?: string; address?: string }): Promise<any> {
    return this.request('/api/auth/my-school', { method: 'PUT', body: JSON.stringify(data) })
  }

  // Platform Admin API
  async getPlatformDashboard(): Promise<any> {
    return this.request('/api/platform-admin/dashboard')
  }

  async listSchools(): Promise<{ schools: any[] }> {
    return this.request('/api/platform-admin/schools')
  }

  async createSchool(data: any): Promise<any> {
    return this.request('/api/platform-admin/schools', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async getSchool(schoolId: string): Promise<any> {
    return this.request(`/api/platform-admin/schools/${schoolId}`)
  }

  async updateSchool(schoolId: string, data: any): Promise<any> {
    return this.request(`/api/platform-admin/schools/${schoolId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    })
  }

  async listPlatformPlans(): Promise<{ plans: any[] }> {
    return this.request('/api/platform-admin/plans')
  }

  async createPlatformPlan(data: any): Promise<any> {
    return this.request('/api/platform-admin/plans', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async listLicenses(): Promise<{ licenses: any[] }> {
    return this.request('/api/platform-admin/licenses')
  }

  async createLicense(data: any): Promise<any> {
    return this.request('/api/platform-admin/licenses', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async activateLicense(licenseId: string): Promise<any> {
    return this.request(`/api/platform-admin/licenses/${licenseId}/activate`, {
      method: 'POST',
    })
  }

  async suspendLicense(licenseId: string): Promise<any> {
    return this.request(`/api/platform-admin/licenses/${licenseId}/suspend`, {
      method: 'POST',
    })
  }

  async renewLicense(licenseId: string): Promise<any> {
    return this.request(`/api/platform-admin/licenses/${licenseId}/renew`, {
      method: 'POST',
    })
  }

  async listActivationCodes(): Promise<{ activations: any[] }> {
    return this.request('/api/platform-admin/activations')
  }

  async listLicenseActivationCodes(licenseId: string): Promise<{ activation_codes: any[] }> {
    return this.request(`/api/platform-admin/licenses/${licenseId}/activation-codes`)
  }

  async generateActivationCode(licenseId: string): Promise<any> {
    return this.request(`/api/platform-admin/licenses/${licenseId}/activation-codes`, {
      method: 'POST',
    })
  }

  async resetDemoData(): Promise<any> {
    // Second layer of defense: this method is only invoked from the
    // dev-gated dashboard control, and the backend 403s unless DEBUG is on.
    if (!DEV_TOOLS_ENABLED) {
      return { disabled: true, message: 'Demo reset is unavailable in this build' }
    }
    return this.request('/api/platform-admin/reset-demo-data', {
      method: 'POST',
      body: JSON.stringify({ confirm: 'RESET DEMO COMMERCIAL DATA' }),
    })
  }

  async revokeActivationCode(codeId: string): Promise<any> {
    return this.request(`/api/platform-admin/activations/${codeId}/revoke`, {
      method: 'POST',
    })
  }

  async activateDesktop(code: string): Promise<any> {
    return this.request('/api/platform-admin/activate', {
      method: 'POST',
      body: JSON.stringify({ activation_code: code }),
    })
  }

  async setupAfterActivation(data: {
    email: string
    password: string
    full_name: string
    activation_code: string
    school_id?: string
  }): Promise<any> {
    return this.request('/api/auth/setup-school-admin', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async validateActivationCode(activation_code: string): Promise<any> {
    return this.request('/api/auth/activation/validate', {
      method: 'POST',
      body: JSON.stringify({ activation_code }),
    })
  }

  async updateTeacher(userId: string, data: { full_name?: string; email?: string }): Promise<any> {
    return this.request(`/api/auth/users/${userId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    })
  }

  async listPlatformPayments(status?: string): Promise<{ payments: any[] }> {
    const params = status ? `?status=${status}` : ''
    return this.request(`/api/platform-admin/payments${params}`)
  }

  async platformVerifyPayment(paymentId: string, notes?: string): Promise<any> {
    return this.request(`/api/platform-admin/payments/${paymentId}/verify`, {
      method: 'POST',
      body: JSON.stringify({ notes: notes || '' }),
    })
  }

  async platformRejectPayment(paymentId: string, reason: string): Promise<any> {
    return this.request(`/api/platform-admin/payments/${paymentId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    })
  }

  async listPlatformAuditLogs(limit?: number): Promise<{ logs: any[] }> {
    const params = limit ? `?limit=${limit}` : ''
    return this.request(`/api/platform-admin/audit${params}`)
  }

  // ── Weekly class-teacher plans (Approved WAPEF Basic 1-3 Plan) ─────────────
  // Basic 1-3 only: the class boundary is decided server-side by
  // wapef_template_for_class, and this client never routes Basic 4-JHS here.

  /** Which WAPEF planning model applies to a class (Basic 1-3 boundary). */
  async getWeeklyRouting(classLevel: string): Promise<WeeklyRouting> {
    return this.request(`/api/weekly-plans/routing/${encodeURIComponent(classLevel)}`)
  }

  /** The teaching-day options the teacher assigns per subject. */
  async getWeeklyDayOptions(): Promise<{ days: WeeklyDayOption[]; week_days: string[] }> {
    return this.request('/api/weekly-plans/day-options')
  }

  /** Build a weekly class plan without persisting it. */
  async previewWeeklyPlan(request: WeeklyPlanRequest): Promise<WeeklyPreviewResponse> {
    return this.request('/api/weekly-plans/preview', {
      method: 'POST',
      body: JSON.stringify(request),
    })
  }

  /** Persist one weekly class plan (review -> save -> reload -> edit -> export). */
  async createWeeklyPlan(request: WeeklyPlanRequest): Promise<{ plan: WeeklyClassPlan; id: string }> {
    return this.request('/api/weekly-plans', {
      method: 'POST',
      body: JSON.stringify(request),
    })
  }

  /** The teacher's weekly class plans (newest first). */
  async listWeeklyPlans(): Promise<{ plans: WeeklyPlanListItem[] }> {
    return this.request('/api/weekly-plans')
  }

  /** Fetch one weekly plan (reload after save, with full day-plan content). */
  async getWeeklyPlan(planId: string): Promise<{ plan: WeeklyClassPlan }> {
    return this.request(`/api/weekly-plans/${planId}`)
  }

  /** Edit a saved weekly plan (subject + day granularity, isolation enforced). */
  async updateWeeklyPlan(planId: string, updates: Record<string, unknown>): Promise<{ plan: WeeklyClassPlan }> {
    return this.request(`/api/weekly-plans/${planId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    })
  }

  /** One DOCX: one weekly class plan with every subject section in it. */
  async exportWeeklyDocx(planId: string) {
    return this.exportBlob(`${this.baseUrl}/api/weekly-plans/${planId}/export/docx`)
  }

  /** PDF from the same canonical weekly document (DOCX -> PDF). */
  async exportWeeklyPdf(planId: string) {
    return this.exportBlob(`${this.baseUrl}/api/weekly-plans/${planId}/export/pdf`)
  }

  // Electron file download (native save dialog) / browser blob download
  async downloadFile(blob: Blob, defaultFilename: string): Promise<void> {
    const filename = sanitizeDownloadName(defaultFilename)
    if (this.isElectron) {
      const { ipcRenderer } = window as any
      const result = await ipcRenderer.invoke('save-file', {
        defaultPath: filename,
        filters: [{ name: 'All Files', extensions: ['*'] }]
      })
      if (!result.canceled && result.filePath) {
        const buffer = await blob.arrayBuffer()
        const fs = window.require('fs')
        fs.writeFileSync(result.filePath, Buffer.from(buffer))
      }
    } else {
      // Chrome renders inline-displayable types (PDF) in its viewer instead of
      // saving them when the object URL keeps that MIME — the click produces no
      // download at all. Re-wrap as a generic binary stream so every export is
      // treated as a file download; the filename keeps the correct extension.
      const downloadBlob = blob.type === 'application/pdf'
        ? new Blob([blob], { type: 'application/octet-stream' })
        : blob
      const url = URL.createObjectURL(downloadBlob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.rel = 'noopener'
      a.style.display = 'none'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      // Chrome aborts the download when the object URL is revoked in the same
      // task as the click (Edge is more forgiving, which is why Word downloads
      // failed in Chrome but passed in Edge). Release it on a later tick,
      // after the browser has started reading the blob.
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    }
  }
}

/**
 * An Error carrying the backend's stable, machine-readable failure code.
 * ``message`` is always the teacher-safe text; ``diagnostic`` (when present)
 * holds the raw server-side cause for developer diagnostics only — it is never
 * rendered to the teacher (PART H/AD).
 */
export interface ApiError extends Error {
  code?: string
  diagnostic?: string
}

/**
 * Repair the TermConfig payload at the API boundary (real-use remediation,
 * "Action failed — Validation failed" root cause).
 *
 * The Term Start / Term End date inputs write their value straight into the
 * config state; clearing an HTML date input yields `''`, and the backend's
 * Pydantic model rejects an empty date string with a 422 ("Validation failed").
 * The same class of failure hits class_level / subject when a scheme's
 * detection left them blank. Both Quick Generate and Build with me share this
 * one config state, which is why both paths failed identically.
 *
 * This repair keeps the teacher's intent instead of dead-ending the flow:
 * an emptied date is replaced by the scheme's own curriculum span when the
 * page derived one, and otherwise OMITTED so the backend derives the term
 * window from the scheme — the page never guesses a date. An emptied
 * class/subject falls back to the scheme's detected values. The backend
 * remains the validator of last resort.
 */
export function sanitizeTermConfig(
  config: any,
  fallback?: { term_start_date?: string; term_end_date?: string; class_level?: string; subject?: string }
): any {
  if (!config || typeof config !== 'object') return config
  const DATE_RE = /^\d{4}-\d{2}-\d{2}$/
  const cfg: any = { ...config }

  // An emptied date input is "not set": restore the scheme's own span when it
  // is known, else omit the key — the backend fills it from the curriculum.
  for (const key of ['term_start_date', 'term_end_date'] as const) {
    const value = cfg[key]
    if (typeof value === 'string' && DATE_RE.test(value)) continue
    const fb = fallback?.[key]
    if (fb && DATE_RE.test(fb)) cfg[key] = fb
    else delete cfg[key]
  }
  // Teaching days must be an array of integers 0-6.
  if (!Array.isArray(cfg.teaching_days)) cfg.teaching_days = [0, 2, 4]
  else cfg.teaching_days = cfg.teaching_days.map((d: any) => Number(d)).filter((d: any) => Number.isInteger(d) && d >= 0 && d <= 6)

  // Numeric fields can land as strings from lenient inputs.
  const asInt = (v: any, dflt: number) => {
    const n = parseInt(v, 10)
    return Number.isFinite(n) && n > 0 ? n : dflt
  }
  cfg.lessons_per_week = asInt(cfg.lessons_per_week, 3)
  cfg.lesson_duration_minutes = asInt(cfg.lesson_duration_minutes, 60)
  cfg.class_size = Number.isFinite(Number(cfg.class_size)) && Number(cfg.class_size) > 0
    ? Number(cfg.class_size) : 24

  // The backend enum rejects '' — restore the scheme's detected value or drop
  // the key so the backend default ('Unknown') applies and its own gate can
  // produce a real teacher-facing message instead of a raw 422.
  for (const key of ['class_level', 'subject'] as const) {
    if (typeof cfg[key] !== 'string' || !cfg[key].trim()) {
      const fb = fallback?.[key]
      if (fb && fb !== 'Unknown') cfg[key] = fb
      else delete cfg[key]
    }
  }

  // List fields must be arrays of strings.
  for (const key of ['keywords', 'teaching_learning_resources', 'core_competencies',
                     'references', 'selected_indicator_codes'] as const) {
    if (cfg[key] !== undefined && !Array.isArray(cfg[key])) delete cfg[key]
  }
  if (Array.isArray(cfg.holidays)) {
    cfg.holidays = cfg.holidays.filter((h: any) => h && typeof h === 'object' && typeof h.date === 'string' && DATE_RE.test(h.date))
  }
  return cfg
}

/**
 * Turn a backend error ``detail`` into a safe Error.
 *
 * ``detail`` is normally a plain string (legacy contract). AI endpoints now
 * return ``{ code, message, diagnostic }`` so the teacher sees the calm,
 * user-safe message while the raw provider error is preserved separately.
 */
export function errorFromDetail(detail: unknown): ApiError {
  if (detail && typeof detail === 'object') {
    const d = detail as { code?: string; message?: string; diagnostic?: string }
    const err = new Error(d.message || 'Request failed') as ApiError
    err.code = d.code
    err.diagnostic = d.diagnostic
    return err
  }
  if (typeof detail === 'string' && detail) {
    return new Error(detail)
  }
  return new Error('Request failed')
}

/**
 * A downloaded export: the body plus the filename the server chose.
 * Falls back to a client-side name when the server sent no Content-Disposition.
 */
export interface ExportPayload {
  blob: Blob
  filename: string | null
}

/**
 * Read the filename out of a Content-Disposition header.
 * Prefers RFC 5987 `filename*=UTF-8''...` over the ASCII `filename=`, since the
 * former is what the server uses for non-ASCII names.
 */
export function filenameFromContentDisposition(header: string | null): string | null {
  if (!header) return null
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header)
  if (encoded) {
    try {
      return decodeURIComponent(encoded[1].trim())
    } catch {
      // Malformed percent-encoding: fall through to the plain form.
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header)
  return plain ? plain[1].trim() : null
}

/**
 * Strip characters that browsers/Windows reject or rewrite in a filename, so
 * the saved name matches what the user saw regardless of browser.
 */
export function sanitizeDownloadName(name: string): string {
  const cleaned = (name || '')
    .replace(/[\\/:*?"<>|\x00-\x1f]/g, '_')
    .replace(/^[.\s]+/, '')
    .trim()
  return cleaned || 'download'
}

export const api = new ApiService()
