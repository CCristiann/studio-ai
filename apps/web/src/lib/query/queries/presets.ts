import { queryOptions } from '@tanstack/react-query'
import { fetchPresets } from '../api/presets'

export const presetQueries = {
  all: (token: string) =>
    queryOptions({
      queryKey: ['presets', 'all'] as const,
      queryFn: () => fetchPresets(token),
      enabled: !!token,
    }),
}
