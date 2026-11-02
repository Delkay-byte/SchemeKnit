import type { MetadataRoute } from 'next'
import { IS_STAGING, absoluteUrl } from '@/lib/site-url'

// Static metadata route so the desktop static export can collect it.
export const dynamic = 'force-static'

export default function robots(): MetadataRoute.Robots {
  if (IS_STAGING) {
    return {
      rules: [{ userAgent: '*', disallow: '/' }],
    }
  }
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        disallow: [
          '/api/',
          '/dashboard',
          '/generate',
          '/review',
          '/lessons',
          '/settings',
          '/subscription',
          '/templates',
          '/upgrade',
          '/upload',
          '/weekly-plans',
          '/platform-admin',
          '/school-admin',
          '/payments',
          '/payments/callback',
          '/login',
          '/signup',
          '/reset-password',
          '/setup',
          '/activate',
          '/activate-school',
          '/admin',
        ],
      },
    ],
    sitemap: absoluteUrl('/sitemap.xml'),
    host: absoluteUrl('/'),
  }
}
