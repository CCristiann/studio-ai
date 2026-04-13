import { queryOptions } from '@tanstack/react-query'
import { fetchPreferences } from '../api/preferences'

export const preferencesQueries = {
  all: (token: string) =>
    queryOptions({
      queryKey: ['preferences', 'all'] as const,
      queryFn: () => fetchPreferences(token),
      enabled: !!token,
    }),
}
