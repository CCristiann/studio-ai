import { queryOptions, skipToken } from '@tanstack/react-query'
import { validateToken, pollDeviceToken } from '../api/auth'

export const authQueries = {
  validate: (token: string | null) =>
    queryOptions({
      queryKey: ['auth', 'validate'] as const,
      queryFn: token ? () => validateToken(token) : skipToken,
      refetchInterval: 30_000,
    }),

  deviceToken: (sessionId: string, deviceCode: string, expiresAt: number) =>
    queryOptions({
      queryKey: ['auth', 'device-token', deviceCode] as const,
      queryFn: deviceCode ? () => pollDeviceToken(sessionId, deviceCode) : skipToken,
      refetchInterval: (query) => {
        if (Date.now() >= expiresAt) return false
        if (query.state.data?.status === 'complete') return false
        return 2_000
      },
      retry: false,
    }),
}
