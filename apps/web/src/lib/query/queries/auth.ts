import { queryOptions } from '@tanstack/react-query'
import { validateToken, pollDeviceToken } from '../api/auth'

export const authQueries = {
  validate: (token: string) =>
    queryOptions({
      queryKey: ['auth', 'validate'] as const,
      queryFn: () => validateToken(token),
      enabled: !!token,
      refetchInterval: 30_000,
    }),

  deviceToken: (sessionId: string, deviceCode: string, expiresAt: number) =>
    queryOptions({
      queryKey: ['auth', 'device-token', deviceCode] as const,
      queryFn: () => pollDeviceToken(sessionId, deviceCode),
      enabled: !!deviceCode && Date.now() < expiresAt,
      refetchInterval: (query) => {
        if (Date.now() >= expiresAt) return false
        if (query.state.data?.status === 'complete') return false
        return 2_000
      },
      retry: false,
    }),
}
