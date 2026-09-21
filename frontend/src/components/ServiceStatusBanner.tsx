'use client'

import { useState, useEffect } from 'react'
import { useServiceStatus } from '@/hooks/useServiceStatus'

export function ServiceStatusBanner() {
  const { status, isOnline, isMaintenance, maintenanceMessage } = useServiceStatus()
  const [showBanner, setShowBanner] = useState(false)
  const [bannerMessage, setBannerMessage] = useState('')
  const [bannerType, setBannerType] = useState<'offline' | 'maintenance' | 'recovery'>('offline')
  const [hasNotifiedRecovery, setHasNotifiedRecovery] = useState(false)

  useEffect(() => {
    if (isMaintenance) {
      setBannerType('maintenance')
      setBannerMessage(maintenanceMessage || 'SchemeKnit is currently undergoing maintenance. We\'ll be back shortly.')
      setShowBanner(true)
      setHasNotifiedRecovery(false)
    } else if (status === 'offline') {
      setBannerType('offline')
      setBannerMessage('SchemeKnit server is currently unavailable. We\'ll reconnect automatically.')
      setShowBanner(true)
      setHasNotifiedRecovery(false)
    } else if (isOnline && showBanner && !hasNotifiedRecovery) {
      // Transition from offline/maintenance to healthy
      setBannerType('recovery')
      setBannerMessage('SchemeKnit is back online.')
      setShowBanner(true)
      setHasNotifiedRecovery(true)

      // Auto-dismiss recovery message after 5 seconds
      const timer = setTimeout(() => {
        setShowBanner(false)
      }, 5000)
      return () => clearTimeout(timer)
    } else if (isOnline && !showBanner) {
      setShowBanner(false)
    }
  }, [status, isOnline, isMaintenance, maintenanceMessage, showBanner, hasNotifiedRecovery])

  // Listen for custom events from the service status hook
  useEffect(() => {
    const handleServerDown = () => {
      setBannerType('offline')
      setBannerMessage('SchemeKnit server is currently unavailable. We\'ll reconnect automatically.')
      setShowBanner(true)
      setHasNotifiedRecovery(false)
    }

    const handleBackOnline = () => {
      setBannerType('recovery')
      setBannerMessage('SchemeKnit is back online.')
      setShowBanner(true)
      setHasNotifiedRecovery(true)
      setTimeout(() => setShowBanner(false), 5000)
    }

    const handleMaintenance = (e: CustomEvent) => {
      setBannerType('maintenance')
      setBannerMessage(e.detail?.message || 'SchemeKnit is currently undergoing maintenance.')
      setShowBanner(true)
      setHasNotifiedRecovery(false)
    }

    const handleMaintenanceEnded = () => {
      setBannerType('recovery')
      setBannerMessage('SchemeKnit maintenance has ended.')
      setShowBanner(true)
      setHasNotifiedRecovery(true)
      setTimeout(() => setShowBanner(false), 5000)
    }

    window.addEventListener('schemeknit:server-down', handleServerDown)
    window.addEventListener('schemeknit:back-online', handleBackOnline)
    window.addEventListener('schemeknit:maintenance', handleMaintenance as EventListener)
    window.addEventListener('schemeknit:maintenance-ended', handleMaintenanceEnded)

    return () => {
      window.removeEventListener('schemeknit:server-down', handleServerDown)
      window.removeEventListener('schemeknit:back-online', handleBackOnline)
      window.removeEventListener('schemeknit:maintenance', handleMaintenance as EventListener)
      window.removeEventListener('schemeknit:maintenance-ended', handleMaintenanceEnded)
    }
  }, [])

  if (!showBanner) return null

  const bgColor = bannerType === 'maintenance'
    ? 'bg-amber-50 border-amber-200'
    : bannerType === 'offline'
    ? 'bg-red-50 border-red-200'
    : 'bg-green-50 border-green-200'

  const textColor = bannerType === 'maintenance'
    ? 'text-amber-800'
    : bannerType === 'offline'
    ? 'text-red-800'
    : 'text-green-800'

  const icon = bannerType === 'maintenance'
    ? '🔧'
    : bannerType === 'offline'
    ? '⚠️'
    : '✅'

  return (
    <div className={`fixed top-0 left-0 right-0 z-50 ${bgColor} border-b ${textColor} px-4 py-3 shadow-sm`}>
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-lg">{icon}</span>
          <div>
            <p className="font-medium text-sm">{bannerMessage}</p>
            {bannerType === 'maintenance' && (
              <p className="text-xs opacity-75 mt-0.5">Some actions may be temporarily unavailable.</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {bannerType !== 'recovery' && (
            <button
              onClick={() => window.location.reload()}
              className="text-xs px-3 py-1 rounded border border-current opacity-75 hover:opacity-100 transition-opacity"
            >
              Retry
            </button>
          )}
          <button
            onClick={() => setShowBanner(false)}
            className="text-xs opacity-50 hover:opacity-100 transition-opacity"
            aria-label="Dismiss"
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  )
}
