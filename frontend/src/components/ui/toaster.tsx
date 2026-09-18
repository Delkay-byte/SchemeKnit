'use client'

import { useEffect, useState } from 'react'

interface Toast {
  id: string
  title: string
  description?: string
  variant?: 'default' | 'destructive'
}

let toastId = 0

export function toast(options: { title: string; description?: string; variant?: 'default' | 'destructive' }) {
  const id = String(++toastId)
  const event = new CustomEvent('toast', { detail: { ...options, id } })
  window.dispatchEvent(event)
  return id
}

export function Toaster() {
  const [toasts, setToasts] = useState<Toast[]>([])

  useEffect(() => {
    const handleToast = (e: CustomEvent<Toast>) => {
      setToasts(prev => [...prev, e.detail])
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== e.detail.id))
      }, 5000)
    }

    window.addEventListener('toast', handleToast as EventListener)
    return () => window.removeEventListener('toast', handleToast as EventListener)
  }, [])

  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 space-y-2">
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`p-4 rounded-lg shadow-lg max-w-sm ${
            toast.variant === 'destructive'
              ? 'bg-destructive text-destructive-foreground'
              : 'bg-background border'
          }`}
        >
          <div className="font-medium">{toast.title}</div>
          {toast.description && (
            <div className="text-sm opacity-80">{toast.description}</div>
          )}
        </div>
      ))}
    </div>
  )
}