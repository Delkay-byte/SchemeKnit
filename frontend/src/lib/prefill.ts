/**
 * Teacher-facing prefill rules.
 *
 * Authoritative server values always win. Profile values only fill fields the
 * teacher has left blank, and only for the signed-in user. Nothing here invents
 * curriculum data.
 */

export interface TeacherProfileDefaults {
  full_name?: string | null
  school_name?: string | null
}

export interface PrefillableLessonConfig {
  teacher_name?: string | null
  school_name?: string | null
}

function clean(value: string | null | undefined): string {
  return (value || '').trim()
}

export function prefillLessonConfig<T extends PrefillableLessonConfig>(
  config: T,
  profile: TeacherProfileDefaults | null | undefined,
): T {
  return {
    ...config,
    teacher_name: clean(config.teacher_name) || clean(profile?.full_name) || null,
    school_name: clean(config.school_name) || clean(profile?.school_name) || null,
  }
}
