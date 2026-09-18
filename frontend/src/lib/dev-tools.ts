/**
 * Development-only tooling gate.
 *
 * Acceptance/demo tooling (e.g. the demo commercial-data reset) must never be
 * reachable in a production deployment. This flag is resolved at BUILD time:
 *
 *  - `process.env.NODE_ENV` is inlined by Next.js/webpack, so when the app is
 *    built for production the expression below folds to `false` and dead-code
 *    elimination drops the guarded control from the bundle.
 *  - Locally, `NEXT_PUBLIC_DEV_TOOLS=true` (in frontend/.env.local) opts the
 *    tools back in for development and acceptance runs.
 *
 * This is one of three layers; the backend also refuses the reset route with
 * 403 whenever DEBUG is off, so even a hand-crafted request cannot run it
 * against a production database.
 */
export const DEV_TOOLS_ENABLED: boolean =
  process.env.NODE_ENV === 'development' &&
  process.env.NEXT_PUBLIC_DEV_TOOLS === 'true'
