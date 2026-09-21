'use client'

import { useState, useEffect, useCallback, useRef } from 'react'

type ServiceStatus = 'healthy' | 'degraded' | 'offline' | 'maintenance' | 'unknown'

interface MaintenanceInfo {
  active: boolean
  message: string
  estimated_restore: string
}

interface ServiceStatusResponse {
  status: ServiceStatus
  maintenance: MaintenanceInfo
  version: string
}

interface UseServiceStatusReturn {
  status: ServiceStatus
  isOnline: boolean
  isMaintenance: boolean
  maintenanceMessage: string
  lastChecked: Date | null
  error: string | null
}

const CHECK_INTERVAL_MS = 30000 // 30 seconds
const CONSECUTIVE_FAILURES_THRESHOLD = 3
const RETRY_BACKOFF_MS = [2000, 5000, 10000] // progressive backoff

export function useServiceStatus(apiBaseUrl: string = ''): UseServiceStatusReturn {
  const [status, setStatus] = useState<ServiceStatus>('unknown')
  const [maintenanceInfo, setMaintenanceInfo] = useState<MaintenanceInfo>({
    active: false,
    message: '',
    estimated_restore: '',
  })
  const [lastChecked, setLastChecked] = useState<Date | null>(null)
  const [error, setError] = useState<string | null>(null)

  const consecutiveFailures = useRef(0)
  const previousStatus = useRef<ServiceStatus>('unknown')
  const retryIndex = useRef(0)
  const intervalRef = useRef<NodeJS.Timeout | null>(null)
  const mountedRef = useRef(true)

  const baseUrl = apiBaseUrl || ''

  const checkStatus = useCallback(async () => {
    if (!mountedRef.current) return

    try {
      const controller = new AbortController()
      const timeoutId = setTimeout(() => controller.abort(), 10000) // 10s timeout

      const response = await fetch(`${baseUrl}/api/service-status`, {
        method: 'GET',
        signal: controller.signal,
        headers: { 'Accept': 'application/json' },
      })

      clearTimeout(timeoutId)

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data: ServiceStatusResponse = await response.json()

      if (!mountedRef.current) return

      // Reset failure tracking
      consecutiveFailures.current = 0
      retryIndex.current = 0

      const newStatus = data.status || 'healthy'
      const prevStatus = previousStatus.current

      // Update status
      setStatus(newStatus)
      setMaintenanceInfo(data.maintenance || { active: false, message: '', estimated_restore: '' })
      setLastChecked(new Date())
      setError(null)

      // State transition notifications
      if (prevStatus === 'offline' && newStatus === 'healthy') {
        // Back online — will be handled by the component
        window.dispatchEvent(new CustomEvent('schemeknit:back-online'))
      }
      if (prevStatus !== 'maintenance' && newStatus === 'maintenance') {
        window.dispatchEvent(new CustomEvent('schemeknit:maintenance', {
          detail: data.maintenance,
        }))
      }
      if (prevStatus === 'maintenance' && newStatus === 'healthy') {
        window.dispatchEvent(new CustomEvent('schemeknit:maintenance-ended'))
      }

      previousStatus.current = newStatus
    } catch (err) {
      if (!mountedRef.current) return

      consecutiveFailures.current += 1

      if (consecutiveFailures.current >= CONSECUTIVE_FAILURES_THRESHOLD) {
        const newStatus: ServiceStatus = 'offline'
        setStatus(newStatus)
        setError('Server unavailable')

        // State transition: healthy → offline
        if (previousStatus.current !== 'offline') {
          window.dispatchEvent(new CustomEvent('schemeknit:server-down'))
        }
        previousStatus.current = newStatus
      } else {
        // Transient failure — don't change status yet
        setError(`Check failed (${consecutiveFailures.current}/${CONSECUTIVE_FAILURES_THRESHOLD})`)
      }

      setLastChecked(new Date())
    }
  }, [baseUrl])

  // Start/stop polling
  useEffect(() => {
    mountedRef.current = true

    // Initial check
    checkStatus()

    // Set up interval with backoff
    const scheduleNext = () => {
      if (!mountedRef.current) return
      const delay = RETRY_BACKOFF_MS[Math.min(retryIndex.current, RETRY_BACKOFF_MS.length - 1)]
      intervalRef.current = setTimeout(() => {
        checkStatus().then(() => {
          if (mountedRef.current) {
            scheduleNext()
          }
        })
      }, CHECK_INTERVAL_MS + (consecutiveFailures.current > 0 ? delay : 0))
    }

    scheduleNext()

    return () => {
      mountedRef.current = false
      if (intervalRef.current) {
        clearTimeout(intervalRef.current)
      }
    }
  }, [checkStatus])

  return {
    status,
    isOnline: status === 'healthy',
    isMaintenance: status === 'maintenance',
    maintenanceMessage: maintenanceInfo.message,
    lastChecked,
    error,
  }
}
