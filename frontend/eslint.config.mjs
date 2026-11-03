import nextVitals from 'eslint-config-next/core-web-vitals'
import nextTypeScript from 'eslint-config-next/typescript'
import globals from 'globals'

export default [
  {
    ignores: [
      '.next/**',
      'out/**',
      'node_modules/**',
      'next-env.d.ts',
      '*.tsbuildinfo',
      'public/**',
    ],
  },
  ...nextVitals,
  ...nextTypeScript,
  {
    rules: {
      // Existing code uses `any` at third-party and API boundaries. Keep the
      // rule visible as a warning; TypeScript strict mode still gates types.
      '@typescript-eslint/no-explicit-any': 'warn',
      // React Hooks v7 introduces compiler-oriented rules that the existing
      // effect/state architecture does not yet satisfy. They are reviewed as
      // warnings, not suppressed outright.
      'react-hooks/set-state-in-effect': 'warn',
      'react-hooks/immutability': 'warn',
      'react-hooks/refs': 'warn',
      'react-hooks/purity': 'warn',
    },
  },
  {
    files: ['e2e/**/*.js', 'tests/**/*.ts'],
    languageOptions: {
      globals: { ...globals.node },
    },
    rules: {
      '@typescript-eslint/no-require-imports': 'off',
    },
  },
]
