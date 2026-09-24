'use client'

import Link from 'next/link'
import { CurriculumPipeline } from './curriculum-pipeline'
import { MeshBackground } from '@/components/mesh-background'
import styles from './landing-hero.module.css'

export function scrollToSection(id: string) {
  const target = document.getElementById(id)
  if (!target) return
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  target.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
}

export function LandingHero() {
  return (
    <section className={styles.hero} aria-labelledby="hero-heading">
      {/* Interactive curriculum mesh — behind copy + pipeline, never overpowering */}
      <MeshBackground mode="hero" className={styles.meshLayer} opacity={0.95} />
      <div className={styles.heroInner}>
        <div className={styles.copy}>
          <p className={styles.eyebrow}>Ghana&apos;s curriculum-grounded lesson planner</p>
          <h1 id="hero-heading" className={styles.headline}>
            <span className={styles.line}>Turn Your Scheme</span>
            <span className={styles.line}>Into the Right Lesson.</span>
          </h1>
          <p className={styles.support}>
            Upload your real scheme of learning. SchemeKnit maps the curriculum, follows the
            right indicator and teaching period, and builds a teacher-ready lesson without
            drifting away from your scheme.
          </p>
          <div className={styles.actions}>
            <Link href="/login" className={styles.primary}>
              Start Planning
            </Link>
            <a
              href="#how-it-works"
              className={styles.secondary}
              onClick={(event) => {
                event.preventDefault()
                scrollToSection('how-it-works')
              }}
            >
              See How It Works
            </a>
          </div>
        </div>
        <CurriculumPipeline />
      </div>
    </section>
  )
}
