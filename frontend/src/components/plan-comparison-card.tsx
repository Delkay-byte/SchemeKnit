'use client'

import { Check, X } from 'lucide-react'

interface Feature {
  label: string
  free: boolean | string
  pro: boolean | string
}

const FEATURES: Feature[] = [
  { label: 'Account', free: true, pro: true },
  { label: 'Upload DOCX or PDF scheme', free: true, pro: true },
  { label: 'Review extracted curriculum', free: true, pro: true },
  { label: 'Configure lessons', free: true, pro: true },
  { label: 'Generate indicator-level plans', free: '2 per month', pro: '20–480 credits' },
  { label: 'Multiple plans from one scheme week', free: true, pro: true },
  { label: 'Download individual DOCX / PDF', free: true, pro: true },
  { label: 'Batch generation within credits', free: 'Within 2 credits', pro: 'Within package credits' },
  { label: 'Flexible credits that never expire', free: false, pro: 'GH₵12 pack' },
  { label: 'Saved work after package ends', free: true, pro: true },
  { label: 'Payment methods', free: 'None needed', pro: 'Bank Transfer / Mobile Money' },
  { label: 'Automatic renewal', free: false, pro: false },
]

function CellIcon({ value }: { value: boolean | string }) {
  if (value === true) {
    return <Check className="h-5 w-5 text-emerald-500" />
  }
  if (value === false) {
    return <X className="h-5 w-5 text-red-400" />
  }
  return <span className="text-sm text-gray-600">{value}</span>
}

export function PlanComparisonCard() {
  return (
    <div className="w-full max-w-3xl mx-auto my-8">
      <h3 className="text-lg font-semibold text-center text-gray-800 mb-4">
        Choose Your Plan
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Free Tier Card */}
        <div className="rounded-xl border-2 border-gray-200 bg-white p-6 shadow-sm">
          <div className="text-center mb-4">
            <h4 className="text-xl font-bold text-gray-800">Free</h4>
            <p className="text-sm text-gray-500 mt-1">Two plans every month</p>
          </div>
          <div className="space-y-3">
            {FEATURES.map((f) => (
              <div key={f.label} className="flex items-center justify-between py-1.5 border-b border-gray-50 last:border-0">
                <span className="text-sm text-gray-700">{f.label}</span>
                <CellIcon value={f.free} />
              </div>
            ))}
          </div>
        </div>

        {/* Pro Card */}
        <div className="rounded-xl border-2 border-emerald-400 bg-white p-6 shadow-md relative">
          <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-emerald-500 text-white text-xs font-bold px-3 py-1 rounded-full">
            RECOMMENDED
          </div>
          <div className="text-center mb-4">
            <h4 className="text-xl font-bold text-emerald-700">Prepaid packages</h4>
            <p className="text-sm text-gray-500 mt-1">Buy credits when you need more</p>
          </div>
          <div className="space-y-3">
            {FEATURES.map((f) => (
              <div key={f.label} className="flex items-center justify-between py-1.5 border-b border-gray-50 last:border-0">
                <span className="text-sm text-gray-700">{f.label}</span>
                <CellIcon value={f.pro} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
