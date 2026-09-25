// SchemeKnit Types — Milestone 2

// ── Approved WAPEF Plan: teacher-selected structured fields ─────────────
// These are TEACHER selections from the approved option lists (served by
// GET /api/generation/wapef/options) — never AI-chosen, never rewritten by
// generation. Spellings are the approved ones and must not be altered.
export interface WapefOptions {
  deep_hopes: string[]
  storylines: string[]
  through_lines: string[]
  gods_story: string[]
}

export interface WapefSelection {
  wapef_deep_hope?: string
  wapef_storyline?: string
  wapef_through_lines?: string[]
  wapef_gods_story?: string
  remarks?: string
}

export type EducationalLevel = 'Early Childhood' | 'Primary' | 'Junior High School' | 'Senior High School'

export type ClassLevel =
  | 'Nursery' | 'KG 1' | 'KG 2'
  | 'Basic 1' | 'Basic 2' | 'Basic 3' | 'Basic 4' | 'Basic 5' | 'Basic 6'
  | 'Basic 7' | 'Basic 8' | 'Basic 9'
  | 'SHS 1' | 'SHS 2' | 'SHS 3'

export type TemplateFamily = 'early_childhood' | 'primary' | 'jhs' | 'shs'

export type ContentSource = 'scheme' | 'deterministic' | 'ai' | 'teacher' | 'template' | 'default'
export type ProductEdition = 'free' | 'teacher' | 'school'

export const CLASS_LEVELS: { value: ClassLevel; label: string; group: string }[] = [
  { value: 'Nursery', label: 'Nursery', group: 'Early Childhood' },
  { value: 'KG 1', label: 'KG 1', group: 'Early Childhood' },
  { value: 'KG 2', label: 'KG 2', group: 'Early Childhood' },
  { value: 'Basic 1', label: 'Basic 1', group: 'Primary' },
  { value: 'Basic 2', label: 'Basic 2', group: 'Primary' },
  { value: 'Basic 3', label: 'Basic 3', group: 'Primary' },
  { value: 'Basic 4', label: 'Basic 4', group: 'Primary' },
  { value: 'Basic 5', label: 'Basic 5', group: 'Primary' },
  { value: 'Basic 6', label: 'Basic 6', group: 'Primary' },
  { value: 'Basic 7', label: 'Basic 7 / JHS 1', group: 'Junior High School' },
  { value: 'Basic 8', label: 'Basic 8 / JHS 2', group: 'Junior High School' },
  { value: 'Basic 9', label: 'Basic 9 / JHS 3', group: 'Junior High School' },
  { value: 'SHS 1', label: 'SHS 1', group: 'Senior High School' },
  { value: 'SHS 2', label: 'SHS 2', group: 'Senior High School' },
  { value: 'SHS 3', label: 'SHS 3', group: 'Senior High School' },
]

export const EDUCATIONAL_LEVELS: { value: EducationalLevel; classLevels: ClassLevel[] }[] = [
  { value: 'Early Childhood', classLevels: ['Nursery', 'KG 1', 'KG 2'] },
  { value: 'Primary', classLevels: ['Basic 1', 'Basic 2', 'Basic 3', 'Basic 4', 'Basic 5', 'Basic 6'] },
  { value: 'Junior High School', classLevels: ['Basic 7', 'Basic 8', 'Basic 9'] },
  { value: 'Senior High School', classLevels: ['SHS 1', 'SHS 2', 'SHS 3'] },
]

export interface SchemeOfWork {
  id: string
  filename: string
  subject: string
  class_level: string
  educational_level?: string
  term: string
  academic_year: string
  weeks_count: number
  status: string
  upload_date?: string
}

export interface Week {
  id: string
  week_number: number
  week_type: string
  start_date: string
  end_date: string
  week_ending_derived?: boolean
  strand: string
  sub_strand: string
  content_standards: string[]
  indicators: string[]
  resources: string[]
}

export interface ReferenceEntry {
  type: string
  title: string
  author_publisher?: string
  page?: string
  notes?: string
}

/** Pre-generation per-lesson review row (source fields read-only). */
export interface LessonReviewSeed {
  lesson_sequence: number
  indicator_code: string
  indicator_description: string
  content_standard_code?: string
  content_standard?: string
  strand?: string
  sub_strand?: string
  source_week: number
  week_ending?: string | null
  week_ending_derived?: boolean
  teaching_week: number
  source_tlrs: string[]
  keywords: string[]
  other_tlrs: string[]
  core_competencies: string[]
  structured_references: ReferenceEntry[]
}

export interface TermConfig {
  scheme_of_work_id: string
  academic_year?: string
  term?: string
  class_level?: string
  subject?: string
  term_start_date: string
  term_end_date: string
  lessons_per_week: number
  lesson_duration_minutes: number
  class_size: number
  teaching_days: number[]
  holidays: Holiday[]
  ai_mode: string
  template_type?: string
  template_id?: string
  include_special_weeks: boolean
  school_name?: string
  teacher_name?: string
  // Lesson metadata supplied once by the teacher (PART 11-24). All optional;
  // blanks stay blank and are never invented by the generator.
  period?: string
  keywords?: string[]
  teaching_learning_resources?: string[]
  core_competencies?: string[]
  references?: string[]
  // Free Tier: which indicators the teacher chose to spend this month's
  // lesson-plan units on. Empty = all indicators (paid/unlimited).
  selected_indicator_codes?: string[]
}

export interface Holiday {
  id: string
  name: string
  date: string
  is_recurring: boolean
  description?: string
}

export interface CurriculumCoverage {
  total_instructional_weeks: number
  total_indicators: number
  total_generated_lessons: number
  indicators_allocated: number
  indicators_unallocated: number
  coverage_percentage: number
  warnings: string[]
}

export interface CurriculumProfile {
  name: string
  educational_level: string
  lessons_per_week: number
  lesson_duration_minutes: number
  features: string[]
}

export interface TemplateField {
  id: string
  name: string
  label: string
  field_type: string
  required: boolean
  visible: boolean
  order: number
  source: ContentSource
}

export interface TemplateSection {
  id: string
  name: string
  label: string
  visible: boolean
  required: boolean
  order: number
  fields: TemplateField[]
}

export interface Template {
  id: string
  name: string
  family: TemplateFamily
  educational_level: EducationalLevel
  description: string
  features: string[]
  sections: TemplateSection[]
  is_default: boolean
  is_official: boolean
  version: string
  author: string
  // Teacher-facing grouping + visibility (PART 9/10/29). The backend returns
  // these on the listing endpoint; they are optional so other endpoints that
  // serialize a template without them still type-check.
  approved_group?: string
  is_custom?: boolean
  provenance?: { verified?: boolean; status?: string; source?: string }
  section_count?: number
  source_type?: string
}

export interface LearningObjective {
  id: string
  description: string
  indicator_code?: string
  source: ContentSource
}

export interface TeachingActivity {
  id: string
  phase: string
  description: string
  duration_minutes: number
  resources: string[]
  source: ContentSource
}

export interface LessonPlan {
  id: string
  week_number: number
  lesson_sequence: number
  lesson_date: string
  lesson_number: string
  educational_level: string
  class_level: string
  subject: string
  class_size: number
  duration_minutes: number
  school_name: string
  teacher_name: string
  strand: string
  sub_strand: string
  content_standard: string
  content_standard_code: string
  indicators: string[]
  indicator_codes: string[]
  lesson_topic: string
  essential_questions: string[]
  previous_knowledge: string
  keywords: string[]
  learning_objectives: LearningObjective[]
  core_competencies: string[]
  teaching_learning_resources: string[]
  introduction: string
  starter_activity: string
  main_activities: TeachingActivity[]
  learner_activities: TeachingActivity[]
  teacher_activities: TeachingActivity[]
  group_work: string
  individual_work: string
  assessment: string
  differentiation: string
  remediation: string
  extension: string
  conclusion: string
  reflection: string
  homework: string
  references: string[]
  status: string
  ai_generated: boolean
  teacher_edited: boolean
  template_id?: string
  // Approved WAPEF Plan teacher-selected fields (tpl-wapef-approved-plan).
  wapef_deep_hope?: string
  wapef_storyline?: string
  wapef_through_lines?: string[]
  wapef_gods_story?: string
  remarks?: string
}

export interface GenerationJob {
  id: string
  status: string
  progress: number
  total_lessons: number
  completed_lessons: number
  failed_lessons: number
  error_message?: string
}

export interface Entitlement {
  id: string
  edition: ProductEdition
  features: string[]
  max_schemes: number
  max_lessons_per_scheme: number
  max_templates: number
  ai_enabled: boolean
  advanced_ai_enabled: boolean
  cloud_sync: boolean
  template_import: boolean
  content_library: boolean
  subscription_type?: string | null
  generation_limit?: number
  generations_used?: number
  batch_generation?: boolean
  zip_export?: boolean
  pdf_export?: boolean
  custom_template_limit?: number
  history_limit?: number
  ai_credits?: number
  ai_credits_used?: number
  expires_at?: string | null
}

export interface PlanResolution {
  source: 'individual' | 'school' | 'individual+school' | 'free'
  edition: string
  subscription_type: string | null
  plan_name: string
  generation_limit: number
  generations_used: number
  batch_generation: boolean
  zip_export: boolean
  pdf_export: boolean
  custom_template_limit: number
  history_limit: number
  ai_enabled: boolean
  ai_credits: number
  ai_credits_used: number
  //: True when AI credits are a one-time lifetime allowance (Free Tier).
  ai_lifetime?: boolean
  //: Free Tier lesson-plan allowance is a CALENDAR-MONTH quota (server-derived).
  lesson_quota_period?: string
  lesson_quota_period_key?: string
  lesson_quota_unlimited?: boolean
  lesson_quota_limit?: number
  lesson_quota_remaining?: number | null
  expires_at: string | null
  is_active: boolean
  school_name: string | null
}

export interface ContentPack {
  id: string
  name: string
  description: string
  class_level: string
  subject: string
  term: string
  academic_year: string
  educational_level: string
  template_family: string
  version: string
  author: string
  is_official: boolean
  is_premium: boolean
  price: number
  lesson_count: number
  status: string
}

// ── Weekly class-teacher plan (Approved WAPEF Basic 1-3 Plan) ────────────────
// Basic 1-3 is the class-teacher model: ONE teacher -> MULTIPLE subjects ->
// DIFFERENT days -> ONE weekly plan document. Basic 4-JHS keeps the
// subject-teacher Approved WAPEF Plan and never enters these flows.

/** Which WAPEF planning model applies to a class (the routing boundary). */
export interface WeeklyRouting {
  class_level: string
  template_id: string
  template_name: string
  planning_model: 'class_teacher' | 'subject_teacher'
  basic13_template_id: string
  subject_teacher_template_id: string
  class_levels: string[]
}

/** One teaching-day option the teacher assigns per subject. */
export interface WeeklyDayOption {
  label: string
  value: string
}

/** One subject the class teacher wants in this week's plan. */
export interface WeeklyPlanSubjectRequest {
  scheme_id: string
  /** Teacher-confirmed day groups: one entry per shared teaching row
   *  (e.g. ["MONDAY", "THURSDAY"] renders as "MONDAY & THURSDAY"). */
  teaching_day_groups: string[][]
  wapef_deep_hope?: string
  wapef_storyline?: string
  wapef_through_lines?: string[]
  wapef_gods_story?: string
  keywords?: string[]
  core_competencies?: string[]
  other_tlrs?: string[]
}

/** Request body for generating one Basic 1-3 weekly class plan. */
export interface WeeklyPlanRequest {
  class_level: string
  week_number: number
  term_start_date: string
  term_end_date: string
  term: string
  academic_year: string
  class_size?: number
  lesson_duration_minutes?: number
  subjects: WeeklyPlanSubjectRequest[]
}

/** One teaching-day entry in a week's subject section. */
export interface WeeklyDayPlan {
  lesson_plan_id?: string | null
  days: string[]
  day_label: string
  focus_indicators: string[]
  focus_indicator_codes: string[]
  starter: string
  main_activities: { phase?: string; description?: string; [k: string]: unknown }[]
  reflection: string
  resources: string[]
  lesson_date?: string | null
  period: string
}

/** Curriculum + WAPEF metadata shared by one subject's day plans. */
export interface WeeklySubjectMetadata {
  subject: string
  class_level: string
  week_number: number
  week_ending?: string | null
  week_ending_derived?: boolean
  reference: string
  strand: string
  sub_strand: string
  content_standards: string[]
  content_standard_codes: string[]
  indicators: string[]
  indicator_codes: string[]
  performance_indicators: string[]
  teaching_learning_resources: string[]
  core_competencies: string[]
  keywords: string[]
  wapef_deep_hope: string
  wapef_storyline: string
  wapef_through_lines: string[]
  wapef_gods_story: string
}

/** One subject section of a weekly class plan. */
export interface WeeklySubjectPlan {
  scheme_of_work_id: string
  job_id: string
  subject: string
  teaching_days: string[]
  teaching_day_groups: string[][]
  metadata: WeeklySubjectMetadata
  day_plans: WeeklyDayPlan[]
}

/** One weekly class-teacher plan holding every subject of the class. */
export interface WeeklyClassPlan {
  id: string
  owner_id: string
  class_level: string
  week_number: number
  term: string
  academic_year: string
  term_start_date?: string | null
  term_end_date?: string | null
  school_name?: string | null
  teacher_name?: string | null
  template_id: string
  subjects: WeeklySubjectPlan[]
  created_date: string
  updated_date: string
}

/** Subject -> teaching days summary shown alongside a preview. */
export interface WeeklyTeachingDaysSummary {
  subject: string
  scheme_of_work_id: string
  teaching_days: string[]
  teaching_day_groups: string[][]
}

export interface WeeklyPreviewResponse {
  plan: WeeklyClassPlan
  teaching_days: WeeklyTeachingDaysSummary[]
  validation_issues: string[]
}

/** Summary row of a saved weekly plan (list view). */
export interface WeeklyPlanListItem {
  id: string
  class_level: string
  week_number: number
  term: string
  academic_year: string
  template_id: string
  school_name?: string | null
  subjects: string[]
  created_date: string
  updated_date: string
}
