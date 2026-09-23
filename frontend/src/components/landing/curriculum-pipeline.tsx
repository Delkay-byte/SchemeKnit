'use client'

import { useEffect, useState } from 'react'
import { SchemeKnitMark } from '@/components/scheme-knit-mark'
import styles from './landing-hero.module.css'

/**
 * Illustrative curriculum → lesson sequence.
 * Nothing here is a live upload or a generated lesson.
 * Motion only changes emphasis; every label stays in the document.
 */

const STAGES = [
  'scheme',
  'subject',
  'indicator',
  'period',
  'engine',
  'lesson',
  'ready',
  'settle',
] as const

type Stage = (typeof STAGES)[number]

const DWELL: Record<Stage, number> = {
  scheme: 1700,
  subject: 1600,
  indicator: 1900,
  period: 1600,
  engine: 1900,
  lesson: 2400,
  ready: 2100,
  settle: 1300,
}

const CAPTION: Record<Stage, string> = {
  scheme: 'Example scheme · Basic 8',
  subject: 'Subject read from the scheme · Science',
  indicator: 'Indicator selected · B8.1.2.1.2',
  period: 'Teaching period 2',
  engine: 'Curriculum sets the bounds',
  lesson: 'Lesson structure for this indicator',
  ready: 'Teacher-ready lesson',
  settle: 'Example workflow',
}

const STATIC_CAPTION =
  'Example: Basic 8 Science, indicator B8.1.2.1.2, teaching period 2'

const PROGRESS = ['scheme', 'subject', 'indicator', 'period', 'engine', 'lesson', 'ready'] as const
type NodeId = (typeof PROGRESS)[number]

function tone(node: NodeId, stage: Stage): 'idle' | 'active' | 'done' {
  if (stage === 'settle') return 'done'
  if (node === 'lesson' && stage === 'ready') return 'active'
  const at = PROGRESS.indexOf(node)
  const now = PROGRESS.indexOf(stage as NodeId)
  if (now === at) return 'active'
  if (now > at) return 'done'
  return 'idle'
}

const LESSON_PARTS = [
  'Starter',
  'Main learning',
  'Assessment',
  'Plenary',
  'TLRs',
] as const

export function CurriculumPipeline() {
  const [stage, setStage] = useState<Stage>('scheme')
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (reduce.matches) return

    let cancelled = false
    let paused = false
    let timer = 0
    let index = 0

    const schedule = () => {
      if (cancelled || paused) return
      setPlaying(true)
      setStage(STAGES[index])
      const wait = DWELL[STAGES[index]]
      index = (index + 1) % STAGES.length
      timer = window.setTimeout(schedule, wait)
    }

    const onVisibility = () => {
      if (document.hidden) {
        paused = true
        window.clearTimeout(timer)
        return
      }
      if (paused) {
        paused = false
        schedule()
      }
    }

    const onReduce = () => {
      if (!reduce.matches) return
      cancelled = true
      window.clearTimeout(timer)
      setPlaying(false)
      setStage('ready')
    }

    schedule()
    document.addEventListener('visibilitychange', onVisibility)
    reduce.addEventListener('change', onReduce)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibility)
      reduce.removeEventListener('change', onReduce)
    }
  }, [])

  useEffect(() => {
    const root = document.getElementById('curriculum-pipeline')
    if (!root) return

    const fine = window.matchMedia('(hover: hover) and (pointer: fine) and (min-width: 1024px)')
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (!fine.matches || reduce.matches) return

    const move = (event: PointerEvent) => {
      const rect = root.getBoundingClientRect()
      if (rect.width === 0 || rect.height === 0) return
      const x = (event.clientX - rect.left) / rect.width
      const y = (event.clientY - rect.top) / rect.height
      root.style.setProperty('--mx', `${(x * 100).toFixed(1)}%`)
      root.style.setProperty('--my', `${(y * 100).toFixed(1)}%`)
      root.style.setProperty('--px', ((x - 0.5) * 2).toFixed(3))
      root.style.setProperty('--py', ((y - 0.5) * 2).toFixed(3))
    }

    const leave = () => {
      root.style.setProperty('--px', '0')
      root.style.setProperty('--py', '0')
    }

    root.addEventListener('pointermove', move)
    root.addEventListener('pointerleave', leave)
    return () => {
      root.removeEventListener('pointermove', move)
      root.removeEventListener('pointerleave', leave)
    }
  }, [])

  const caption = playing ? CAPTION[stage] : STATIC_CAPTION
  const schemeTone = tone('scheme', stage)
  const subjectTone = tone('subject', stage)
  const indicatorTone = tone('indicator', stage)
  const periodTone = tone('period', stage)
  const engineTone = tone('engine', stage)
  const lessonTone = tone('lesson', stage)
  const pickTone = indicatorTone === 'active' || periodTone === 'active'
    ? 'active'
    : indicatorTone === 'done' && periodTone !== 'idle'
      ? 'done'
      : indicatorTone

  return (
    <figure className={styles.panel} id="curriculum-pipeline" data-stage={stage} data-playing={playing ? 'on' : 'off'}>
      <figcaption className={styles.panelHead}>
        <span className={styles.exampleFlag}>Example workflow</span>
        <span className={styles.panelCaption}>{caption}</span>
      </figcaption>

      <div className={styles.board}>
        <svg className={styles.wires} viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <path className={styles.wire} d="M46 16 C 62 14, 64 18, 78 20" />
          <path className={styles.wire} d="M46 78 C 60 70, 62 74, 76 68" />
        </svg>
        <span className={`${styles.spark} ${styles.sparkA}`} aria-hidden="true" />
        <span className={`${styles.spark} ${styles.sparkB}`} aria-hidden="true" />
        <span className={`${styles.spark} ${styles.sparkC}`} aria-hidden="true" />

        <article className={`${styles.card} ${styles.doc} ${styles.shiftDoc}`} data-tone={schemeTone}>
          <p className={styles.kicker}>Uploaded scheme</p>
          <p className={styles.level}>Basic 8</p>
          <p className={styles.subject} data-tone={subjectTone}>Science</p>
          <p className={styles.meta}>Term 1 · Week 4</p>
        </article>

        <ul className={`${styles.bits} ${styles.shiftDoc}`} data-tone={subjectTone} aria-label="Curriculum mapped from the example scheme">
          <li className={styles.chip}>Strand</li>
          <li className={styles.chip}>Sub-strand</li>
          <li className={styles.chip}>Content standard</li>
          <li className={`${styles.chip} ${styles.chipCode}`}>
            Indicator
            <strong>B8.1.2.1.2</strong>
          </li>
        </ul>

        <article className={`${styles.card} ${styles.pick} ${styles.shiftDoc}`} data-tone={pickTone}>
          <p className={styles.kicker}>Selected indicator</p>
          <p className={styles.code} data-tone={indicatorTone}>B8.1.2.1.2</p>
          <p className={styles.period} data-tone={periodTone}>Teaching period 2</p>
        </article>

        <article className={`${styles.card} ${styles.engine} ${styles.shiftEngine}`} data-tone={engineTone}>
          <div className={styles.engineTop}>
            <span className={styles.markTile}>
              <SchemeKnitMark size={26} className={styles.mark} />
            </span>
            <div>
              <p className={styles.engineName}>SchemeKnit</p>
              <p className={styles.engineRole}>Lesson engine</p>
            </div>
          </div>
          <div className={styles.badges}>
            <span className={styles.badgeStrong}>Curriculum first</span>
            <span className={styles.badgeQuiet}>AI constrained by your scheme</span>
          </div>
        </article>

        <article className={`${styles.card} ${styles.lesson} ${styles.shiftLesson}`} data-tone={lessonTone}>
          <div className={styles.lessonHead}>
            <p className={styles.kicker}>Teacher-ready lesson</p>
            <p className={styles.ready} data-on={stage === 'ready' || stage === 'settle' ? 'yes' : 'no'}>
              Ready
            </p>
          </div>
          <ul className={styles.parts}>
            {LESSON_PARTS.map((part) => (
              <li key={part} className={styles.part} title={part === 'TLRs' ? 'Teaching and learning resources' : undefined}>
                <span>{part}</span>
                <span className={styles.track} aria-hidden="true">
                  <span className={styles.fill} />
                </span>
              </li>
            ))}
          </ul>
        </article>
      </div>

      <p className={styles.disclaimer}>
        Illustrative example. SchemeKnit follows the scheme you upload — this is not a live file.
      </p>
      <p className={styles.srOnly}>
        Example workflow, not a live upload. A Basic 8 Science Term 1 scheme for week 4 is read.
        The indicator B8.1.2.1.2 is selected for teaching period 2. SchemeKnit keeps the curriculum
        in control and assembles a lesson with starter, main learning, assessment, plenary, and
        teaching and learning resources.
      </p>
    </figure>
  )
}
