# Frontend Linting

SchemeKnit uses ESLint 9 flat config with the Next.js 16 ruleset.

```bash
cd frontend
npm ci
npm run lint
```

`npm run lint` runs:

```bash
eslint src e2e tests --max-warnings=380
```

- Errors fail CI.
- The warning budget is a measured legacy baseline (364 warnings at
  introduction); new warnings above 380 fail the build.
- `@typescript-eslint/no-explicit-any` and React Hooks v7 compiler-oriented
  rules are warnings for the existing codebase. They must not be disabled
  wholesale, and new code should avoid them.
- Generated output (`.next`, `out`, `node_modules`, `next-env.d.ts`,
  `*.tsbuildinfo`, `public`) is ignored.

`next lint` is not used: Next.js 16 removed that command.
