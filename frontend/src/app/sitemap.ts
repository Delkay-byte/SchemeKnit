import type { MetadataRoute } from 'next'
import { IS_STAGING, absoluteUrl } from '@/lib/site-url'

const PUBLIC_PATHS = [
  '/',
  '/about',
  '/features',
  '/how-it-works',
  '/pricing',
  '/help',
  '/contact',
  '/data-retention',
  '/license-subscription',
  '/privacy-policy',
  '/refunds-cancellation',
  '/terms',
  '/cookie-policy',
]

export default function sitemap(): MetadataRoute.Sitemap {
  if (IS_STAGING) return []
  return PUBLIC_PATHS.map((path) => ({
    url: absoluteUrl(path),
    changeFrequency: path === '/' ? 'weekly' : 'monthly',
    priority: path === '/' ? 1 : 0.6,
  }))
}
