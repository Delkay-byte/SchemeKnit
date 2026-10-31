import type { Metadata } from 'next'

const DEFAULT_SITE_URL = 'https://schemeknit-frontend.onrender.com'

export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL || DEFAULT_SITE_URL
).replace(/\/+$/, '')

export const IS_STAGING =
  process.env.NEXT_PUBLIC_STAGING === 'true' ||
  /staging|localhost|127\.0\.0\.1/i.test(SITE_URL)

export function absoluteUrl(path = '/'): string {
  return `${SITE_URL}${path.startsWith('/') ? path : `/${path}`}`
}

const OG_IMAGE = '/icons/icon-512x512.png'

type PageMetaInput = {
  title: string
  description: string
  path: string
  noIndex?: boolean
}

/** Consistent unique metadata for one public page. */
export function pageMetadata({
  title,
  description,
  path,
  noIndex = false,
}: PageMetaInput): Metadata {
  const url = absoluteUrl(path)
  return {
    title,
    description,
    alternates: { canonical: url },
    openGraph: {
      title,
      description,
      url,
      siteName: 'SchemeKnit',
      type: 'website',
      images: [{ url: absoluteUrl(OG_IMAGE), alt: 'SchemeKnit' }],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [absoluteUrl(OG_IMAGE)],
    },
    robots: noIndex || IS_STAGING
      ? { index: false, follow: false, nocache: true }
      : { index: true, follow: true },
  }
}
