'use client'

import { useQuery } from '@tanstack/react-query'
import { usePluginToken } from '@/hooks/use-plugin-auth'
import { authQueries } from '@/lib/query/queries/auth'
import { PluginDashboard } from './plugin-dashboard'
import { PluginLogin } from './plugin-login'

export default function PluginPage() {
  const { token, ready, setToken, clearToken } = usePluginToken()

  // Periodic server-side validation (checks revocation)
  const { isError } = useQuery({
    ...authQueries.validate(token ?? ''),
    enabled: !!token,
  })

  // If validation fails, clear the token
  if (isError && token) {
    clearToken()
  }

  if (!ready) return null

  if (!token) {
    return <PluginLogin onToken={setToken} />
  }

  return <PluginDashboard token={token} onAuthError={clearToken} />
}
