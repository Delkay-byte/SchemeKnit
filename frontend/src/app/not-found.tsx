import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Home, LifeBuoy } from 'lucide-react'

export default function NotFound() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-md rounded-2xl border border-[#102A43]/8 bg-white p-6 text-center shadow-[0_24px_55px_rgba(16,42,67,0.12)]">
        <p className="text-sm font-semibold uppercase tracking-wider text-[#04769B]">404</p>
        <h1 className="mt-2 text-2xl font-bold text-[#102A43]">Page not found</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          The page you are looking for does not exist, or the scheme or lesson
          it pointed to may have been removed.
        </p>
        <div className="mt-6 flex flex-col justify-center gap-2 sm:flex-row">
          <Button asChild>
            <Link href="/dashboard">
              <Home className="mr-2 h-4 w-4" aria-hidden="true" />
              Go to dashboard
            </Link>
          </Button>
          <Button variant="outline" asChild>
            <Link href="/help">
              <LifeBuoy className="mr-2 h-4 w-4" aria-hidden="true" />
              Get help
            </Link>
          </Button>
        </div>
      </div>
    </div>
  )
}
