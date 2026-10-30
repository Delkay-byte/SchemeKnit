import { redirect } from 'next/navigation'

/**
 * The legacy manual-payment page listed pre-approved product plans and old
 * prices. All purchases now go through the prepaid package checkout, so this
 * route simply redirects to the authoritative upgrade page.
 */
export default function PaymentsPage() {
  redirect('/upgrade')
}
