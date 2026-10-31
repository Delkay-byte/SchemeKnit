import { pageMetadata } from '@/lib/site-url'

export const metadata = pageMetadata({
  title: 'Pricing and Lesson-Plan Credits',
  description:
    'SchemeKnit packages and lesson-plan credits for Ghanaian teachers and schools.',
  path: '/pricing',
})

export default function PricingLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return children
}
