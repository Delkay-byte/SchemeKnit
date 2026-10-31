import { SITE_URL, absoluteUrl } from '@/lib/site-url'

/**
 * Factual site-level structured data. No ratings, awards, endorsements,
 * customer counts or pricing claims are included.
 */
export function SiteStructuredData() {
  const data = [
    {
      '@context': 'https://schema.org',
      '@type': 'Organization',
      name: 'SchemeKnit',
      url: SITE_URL,
      logo: absoluteUrl('/icons/icon-512x512.png'),
      description:
        'SchemeKnit helps Ghanaian teachers turn a Scheme of Learning into editable, curriculum-aligned lesson plans.',
    },
    {
      '@context': 'https://schema.org',
      '@type': 'WebSite',
      name: 'SchemeKnit',
      url: SITE_URL,
    },
    {
      '@context': 'https://schema.org',
      '@type': 'SoftwareApplication',
      name: 'SchemeKnit',
      applicationCategory: 'EducationalApplication',
      operatingSystem: 'Web',
      url: SITE_URL,
      description:
        'A lesson-plan generator for Ghanaian KG, primary and JHS teachers. Upload a Scheme of Learning, select indicators, generate and export lesson plans.',
    },
  ]

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  )
}
