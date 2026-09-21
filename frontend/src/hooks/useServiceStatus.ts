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

const CHECK_INTERVAL_MS = 45000 // 45 seconds between stable checks
const CONSECUTIVE_FAILURES_THRESHOLD = 5 // require 5 failures before declaring offline
const RETRY_BACKOFF_MS = [3000, 5000, 8000, 12000] // progressive backoff on failures
const COLD_START_TIMEOUT_MS = 15000 // 15s initial timeout to tolerate Render cold starts

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
  const hasCompletedFirstCheck = useRef(false)

  const baseUrl = apiBaseUrl || ''

  const checkStatus = useCallback(async () => {
    if (!mountedRef.current) return

    try {
      const controller = new AbortController()
      // Use longer timeout on first check to tolerate Render cold starts
      const timeoutMs = hasCompletedFirstCheck.current ? 10000 : COLD_START_TIMEOUT_MS
      const timeoutId = setTimeout(() => controller.abort(), timeoutMs)

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

      hasCompletedFirstCheck.current = true

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

      hasCompletedFirstCheck.current = true
      consecutiveFailures.current += 1

      if (consecutiveFailures.current >= CONSECUTIVE_FAILURES_THRESHOLD) {
        const newStatus: ServiceStatus = 'offline'
        setStatus(newStatus)
        setError('Server unavailable')

        // State transition: not-offline → offline
        if (previousStatus.current !== 'offline') {
          window.dispatchEvent(new CustomEvent('schemeknit:server-down'))
        }
        previousStatus.current = newStatus
      } else {
        // Transient failure — keep current status, do NOT change to offline
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
