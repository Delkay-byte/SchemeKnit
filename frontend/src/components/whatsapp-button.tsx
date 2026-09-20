import { whatsappUrl, CONTACT_PHONE_LOCAL } from '@/lib/contact'

/**
 * Official WhatsApp glyph (inline SVG so no external asset is required and it
 * renders identically in every deployment, web and desktop).
 */
export function WhatsAppIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 32 32"
      aria-hidden="true"
      focusable="false"
      className={className}
      fill="currentColor"
    >
      <path d="M16.004 3.2c-7.06 0-12.8 5.74-12.8 12.8 0 2.26.6 4.47 1.73 6.41L3.2 28.8l6.56-1.72a12.75 12.75 0 0 0 6.24 1.6h.01c7.06 0 12.8-5.74 12.8-12.8 0-3.42-1.33-6.63-3.75-9.05a12.7 12.7 0 0 0-9.05-3.63Zm0 23.17h-.01a10.6 10.6 0 0 1-5.4-1.48l-.39-.23-4.02 1.05 1.07-3.92-.25-.4a10.57 10.57 0 0 1-1.62-5.65c0-5.86 4.77-10.63 10.64-10.63 2.84 0 5.5 1.11 7.51 3.12a10.55 10.55 0 0 1 3.11 7.52c0 5.87-4.77 10.63-10.63 10.63Zm5.83-7.96c-.32-.16-1.89-.93-2.18-1.04-.29-.11-.5-.16-.71.16-.21.32-.82 1.04-1 1.25-.18.21-.37.24-.68.08-.32-.16-1.35-.5-2.57-1.59-.95-.85-1.59-1.9-1.78-2.21-.18-.32-.02-.49.14-.65.14-.14.32-.37.48-.55.16-.18.21-.32.32-.53.11-.21.05-.4-.03-.55-.08-.16-.71-1.72-.98-2.35-.26-.62-.52-.53-.71-.54-.18-.01-.4-.01-.61-.01-.21 0-.55.08-.84.4-.29.32-1.1 1.08-1.1 2.63s1.13 3.05 1.29 3.26c.16.21 2.22 3.39 5.38 4.76.75.32 1.34.52 1.8.66.76.24 1.44.21 1.99.13.61-.09 1.89-.77 2.15-1.52.27-.74.27-1.38.19-1.51-.08-.13-.29-.21-.61-.37Z" />
    </svg>
  )
}

interface WhatsAppButtonProps {
  /** Optional custom opening message (defaults to the canonical enquiry). */
  message?: string
  /** 'floating' = fixed action button; 'inline' = compact header/help action. */
  variant?: 'floating' | 'inline'
  className?: string
}

/**
 * One reusable WhatsApp contact action.
 *
 * - ``floating`` renders a fixed bottom-right action button (desktop + mobile)
 *   that never covers page controls (it sits above the safe area and has a
 *   large touch target).
 * - ``inline`` renders a compact labelled link for headers/help areas.
 */
export function WhatsAppButton({
  message,
  variant = 'floating',
  className = '',
}: WhatsAppButtonProps) {
  const href = whatsappUrl(message)
  const label = `Chat with BloomCore Technologies on WhatsApp (${CONTACT_PHONE_LOCAL})`

  if (variant === 'inline') {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={label}
        title={label}
        className={`inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-[#128C7E] hover:bg-[#25D366]/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ${className}`}
      >
        <WhatsAppIcon className="h-4 w-4 text-[#25D366]" />
        WhatsApp
      </a>
    )
  }

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={label}
      title={label}
      className={`fixed bottom-5 right-5 z-50 inline-flex h-14 w-14 items-center justify-center rounded-full bg-[#25D366] text-white shadow-lg hover:bg-[#1EBE5D] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-offset-2 focus-visible:ring-offset-[#25D366] ${className}`}
    >
      <WhatsAppIcon className="h-7 w-7" />
    </a>
  )
}
