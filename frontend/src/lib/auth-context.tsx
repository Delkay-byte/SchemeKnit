'use client'

import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { api } from '@/lib/api'

interface User {
  id: string
  email: string
  full_name: string
  school_name: string
  is_admin: boolean
  is_active: boolean
  role: string
  school_id: string | null
}

interface AuthContextType {
  user: User | null
  token: string | null
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  loading: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [token, setToken] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Tab-scoped session: read ONLY from sessionStorage (per-tab). A new tab
    // has empty sessionStorage, so it never inherits another tab's login.
    // Legacy shared localStorage tokens are intentionally NOT migrated — a
    // fresh tab must not silently attach to another tab's identity.
    const savedToken = sessionStorage.getItem('teachflow_token')
    const savedUser = sessionStorage.getItem('teachflow_user')
    if (savedToken && savedUser) {
      setToken(savedToken)
      setUser(JSON.parse(savedUser))
      api.setToken(savedToken)
    }
    setLoading(false)
  }, [])

  const login = async (email: string, password: string) => {
    const response = await api.login(email, password)
    setToken(response.access_token)
    setUser(response.user)
    sessionStorage.setItem('teachflow_token', response.access_token)
    sessionStorage.setItem('teachflow_user', JSON.stringify(response.user))
    api.setToken(response.access_token)
  }

  const logout = () => {
    setToken(null)
    setUser(null)
    sessionStorage.removeItem('teachflow_token')
    sessionStorage.removeItem('teachflow_user')
    api.setToken(null)
  }

  return (
    <AuthContext.Provider value={{ user, token, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
