'use client'

import Link from 'next/link'
import { useRef } from 'react'
import { SchemeKnitMark } from '@/components/scheme-knit-mark'
import { LogoParticleCanvas } from './logo-particles'
import styles from './cinematic-hero.module.css'

export function scrollToSection(id: string) {
  const target = document.getElementById(id)
  if (!target) return
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  target.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' })
}

/**
 * Cinematic brand hero.
 *
 * The real SchemeKnit mark is rendered as crisp HTML/SVG at first paint. As
 * the visitor scrolls, a canvas field sampled from the same mark takes over
 * and disperses, then dissipates before the next section. There is no loader,
 * no scroll hijacking and no autoplay: the canvas only changes when scroll
 * progress changes. Reduced-motion users get the complete static hero.
 */
export function LandingHero() {
  const trackRef = useRef<HTMLElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  const markRef = useRef<HTMLSpanElement>(null)
  const logoRef = useRef<HTMLDivElement>(null)
  const copyRef = useRef<HTMLDivElement>(null)
  const cueRef = useRef<HTMLDivElement>(null)

  return (
    <section
      ref={trackRef}
      className={styles.track}
      aria-labelledby="hero-heading"
      data-hero-track
    >
      <div ref={stageRef} className={styles.stage} data-hero-stage data-phase="logo">
        <div className={styles.particleLayer} aria-hidden="true">
          <LogoParticleCanvas
            trackRef={trackRef}
            stageRef={stageRef}
            markRef={markRef}
            logoRef={logoRef}
            copyRef={copyRef}
            cueRef={cueRef}
            className={styles.particleCanvas}
          />
        </div>

        <div className={styles.inner} data-hero-inner>
          <div ref={logoRef} className={styles.logoLockup} data-hero-logo>
            <span
              ref={markRef}
              className={styles.markPlate}
              data-hero-mark
              aria-hidden="true"
            >
              <SchemeKnitMark size={120} className={styles.mark} />
            </span>
            <span className={styles.wordmark}>
              Scheme<span className={styles.wordmarkKnit}>Knit</span>
            </span>
          </div>

          <div ref={copyRef} className={styles.copy} data-hero-copy>
            <p className={styles.eyebrow}>
              Your scheme. Your curriculum. Your plans.
            </p>
            <h1 id="hero-heading" className={styles.headline}>
              <span className={styles.line}>Your Scheme of Learning.</span>
              <span className={styles.line}>Your Lesson Plans.</span>
              <span className={styles.line}>Made Easier.</span>
            </h1>
            <p className={styles.support}>
              Upload the scheme you already teach. SchemeKnit extracts the week,
              strand, sub-strand, content standard and indicators for you to
              review, then builds a separate lesson plan for each indicator you
              choose. Start free with two lesson plans every month.
            </p>
            <div className={styles.actions}>
              <Link href="/signup" className={styles.primary}>
                Start Free
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
              <Link href="/pricing" className={styles.secondary}>
                View Pricing
              </Link>
            </div>
          </div>

          <div ref={cueRef} className={styles.cue} data-hero-cue aria-hidden="true">
            <span>Scroll to explore</span>
            <span className={styles.cueArrow}>↓</span>
          </div>
        </div>

        <div className={styles.lessonIntro} data-hero-intro>
          <p className={styles.lessonEyebrow}>Inside the lesson</p>
          <h2 id="lesson-intro-heading" className={styles.lessonHeading}>
            One scheme. One indicator. One lesson.
          </h2>
          <p className={styles.lessonSupport}>
            The indicator you selected stays attached to the work. SchemeKnit
            assembles the starter, main learning, assessment, plenary and
            teaching resources around it — not around a generic topic.
          </p>
        </div>
      </div>
    </section>
  )
}
