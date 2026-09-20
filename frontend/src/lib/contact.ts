/**
 * Canonical SchemeKnit contact configuration (single source of truth).
 *
 * Every contact affordance — landing page, footers, teacher dashboards,
 * school-admin pages — reads from here. The number, email and opening message
 * are NEVER hard-coded in individual components.
 *
 * Business name: BloomCore Technologies (the company behind SchemeKnit).
 */

/** Local Ghanaian number, shown to users. */
export const CONTACT_PHONE_LOCAL = '0240064668'

/** International (E.164, no +) form used to build the click-to-chat URL. */
export const CONTACT_PHONE_INTERNATIONAL = '+233240064668'

/** Digits-only international form for https://wa.me/<number>. */
export const WHATSAPP_NUMBER = '233240064668'

/** Canonical support/contact mailbox. */
export const CONTACT_EMAIL = 'bloomcoretechnologies@gmail.com'

/** Default opening message. MUST identify BloomCore Technologies. */
export const WHATSAPP_OPENING_MESSAGE =
  'Hello BloomCore Technologies, I would like to enquire about SchemeKnit. ' +
  'Please assist me with licensing, activation, or any other product enquiry.'

/**
 * Build the click-to-chat URL. Opens directly into the WhatsApp conversation
 * with the opening message pre-filled.
 */
export function whatsappUrl(
  message: string = WHATSAPP_OPENING_MESSAGE,
): string {
  return `https://wa.me/${WHATSAPP_NUMBER}?text=${encodeURIComponent(message)}`
}

/** mailto: link for the canonical contact email. */
export function contactMailtoUrl(subject?: string): string {
  const base = `mailto:${CONTACT_EMAIL}`
  return subject ? `${base}?subject=${encodeURIComponent(subject)}` : base
}
