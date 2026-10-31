/**
 * Canonical SchemeKnit contact configuration (single source of truth).
 *
 * Every contact affordance — landing page, footers, teacher dashboards,
 * school-admin pages — reads from here. The numbers, email and opening message
 * are NEVER hard-coded in individual components.
 *
 * Business: BloomCore Technologies (Ghana-registered sole proprietorship).
 */

/** Primary local Ghanaian number, shown to users. Also the WhatsApp number. */
export const CONTACT_PHONE_LOCAL = '0240064668'

/** Secondary local Ghanaian number. Calls only — NOT registered for WhatsApp. */
export const CONTACT_PHONE_LOCAL_2 = '0553976334'

/** International (E.164) form of the primary number. */
export const CONTACT_PHONE_INTERNATIONAL = '+233240064668'

/** International (E.164) form of the secondary number. */
export const CONTACT_PHONE_INTERNATIONAL_2 = '+233553976334'

/** Digits-only international form for https://wa.me/<number>. */
export const WHATSAPP_NUMBER = '233240064668'

/** Canonical support/contact mailbox. */
export const CONTACT_EMAIL = 'bloomcoretechnologies@gmail.com'

/** Registered business name exactly as shown on the certificate. */
export const BUSINESS_NAME = 'BloomCore Technologies'

/** Business registration number from the Registrar of Companies certificate. */
export const BUSINESS_REGISTRATION_NUMBER = 'BN428031125'

/** Registration date shown on the certificate. */
export const BUSINESS_REGISTRATION_DATE = '7 November 2025'

/** Default opening message. MUST identify BloomCore Technologies. */
export const WHATSAPP_OPENING_MESSAGE =
  'Hello BloomCore Technologies, I would like to enquire about SchemeKnit. ' +
  'Please assist me with licensing, activation, or any other product enquiry.'

/**
 * Build the click-to-chat URL. Opens directly into the WhatsApp conversation
 * with the opening message pre-filled. Only the primary number is registered
 * for WhatsApp; never pass the secondary number here.
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

/** tel: link for the primary (call + WhatsApp) number. */
export function contactTelUrl(): string {
  return `tel:${CONTACT_PHONE_INTERNATIONAL}`
}

/** tel: link for the secondary (call only) number. */
export function contactTelUrl2(): string {
  return `tel:${CONTACT_PHONE_INTERNATIONAL_2}`
}
