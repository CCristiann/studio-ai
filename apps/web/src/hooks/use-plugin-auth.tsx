'use client'

import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'

interface PluginAuthContextValue {
  token: string | null
  ready: boolean
  setToken: (token: string) => void
  clearToken: () => void
}

const PluginAuthCtx = createContext<PluginAuthContextValue | null>(null)

export function PluginAuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setTokenState] = useState<string | null>(null)
  const [ready, setReady] = useState(false)
  const queryClient = useQueryClient()

  // Read token from localStorage on mount, check client-side expiry
  useEffect(() => {
    const stored = localStorage.getItem('studio-ai-token')
    if (!stored) {
      setReady(true)
      return
    }

    // Quick client-side JWT expiry check
    try {
      const base64 = stored.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
      const payload = JSON.parse(atob(base64))
      if (!payload.exp || payload.exp * 1000 <= Date.now()) {
        localStorage.removeItem('studio-ai-token')
        setReady(true)
        return
      }
    } catch {
      localStorage.removeItem('studio-ai-token')
      setReady(true)
      return
    }

    setTokenState(stored)
    // Push token to native plugin via IPC
    window.sendToPlugin?.({ type: 'sendToken', payload: { token: stored } })
    setReady(true)
  }, [])

  const setToken = useCallback((t: string) => {
    localStorage.setItem('studio-ai-token', t)
    setTokenState(t)
    window.sendToPlugin?.({ type: 'sendToken', payload: { token: t } })
  }, [])

  const clearToken = useCallback(() => {
    localStorage.removeItem('studio-ai-token')
    setTokenState(null)
    queryClient.clear()
  }, [queryClient])

  return (
    <PluginAuthCtx.Provider value={{ token, ready, setToken, clearToken }}>
      {children}
    </PluginAuthCtx.Provider>
  )
}

export function usePluginToken() {
  const ctx = useContext(PluginAuthCtx)
  if (!ctx) throw new Error('usePluginToken must be used within PluginAuthProvider')
  return ctx
}
