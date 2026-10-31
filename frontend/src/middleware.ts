import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { IS_STAGING } from '@/lib/site-url'

const PRIVATE_PREFIXES = [
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
  '/login',
  '/signup',
  '/reset-password',
  '/setup',
  '/activate',
  '/activate-school',
  '/admin',
]

export function middleware(request: NextRequest) {
  const response = NextResponse.next()
  const path = request.nextUrl.pathname
  const privatePage = PRIVATE_PREFIXES.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`),
  )
  if (IS_STAGING || privatePage) {
    response.headers.set('X-Robots-Tag', 'noindex, nofollow')
  }
  return response
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|icons|favicon.ico).*)'],
}
