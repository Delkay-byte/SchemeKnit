import type { Metadata, Viewport } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Toaster } from '@/components/ui/toaster'
import { AuthProvider } from '@/lib/auth-context'
import { PwaManager } from '@/components/pwa/pwa-manager'
import { DesktopMenuListener } from '@/components/desktop-menu-listener'

const inter = Inter({ subsets: ['latin'] })

const APP_DESCRIPTION =
  'Create, manage and export professional lesson plans for your school.'

export const metadata: Metadata = {
  title: {
    default: 'SchemeKnit — Lesson Plan Generator',
    template: '%s | SchemeKnit',
  },
  description: APP_DESCRIPTION,
  manifest: '/manifest.webmanifest',
  applicationName: 'SchemeKnit',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'default',
    title: 'SchemeKnit',
  },
  icons: {
    icon: [
      { url: '/icons/favicon.ico', sizes: '48x48', type: 'image/x-icon' },
      { url: '/icons/icon-72x72.png', sizes: '72x72', type: 'image/png' },
      { url: '/icons/icon-96x96.png', sizes: '96x96', type: 'image/png' },
      { url: '/icons/icon-128x128.png', sizes: '128x128', type: 'image/png' },
      { url: '/icons/icon-192x192.png', sizes: '192x192', type: 'image/png' },
      { url: '/icons/icon-384x384.png', sizes: '384x384', type: 'image/png' },
      { url: '/icons/icon-512x512.png', sizes: '512x512', type: 'image/png' },
    ],
    apple: [{ url: '/icons/apple-touch-icon.png', sizes: '180x180' }],
    shortcut: '/icons/favicon.ico',
  },
}

export const viewport: Viewport = {
  themeColor: '#102A43',
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <AuthProvider>
          <DesktopMenuListener />
          <div className="min-h-screen bg-background">
            {children}
          </div>
          <Toaster />
          <PwaManager />
        </AuthProvider>
      </body>
    </html>
  )
}
