/**
 * Build target detection.
 *
 * `NEXT_PUBLIC_BUILD_TARGET` is set to "desktop" by the desktop build
 * (`npm run build:desktop`). When set, Platform Admin UI is excluded:
 * no login, no registration, no dashboard, no licensing controls.
 *
 * The desktop app is an end-user application for School Admin,
 * School Teachers, and Individual Teachers only.
 */
export const isDesktop = process.env.NEXT_PUBLIC_BUILD_TARGET === 'desktop'
