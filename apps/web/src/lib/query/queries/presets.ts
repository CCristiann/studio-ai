import { queryOptions, skipToken } from '@tanstack/react-query'
import { fetchPresets } from '../api/presets'

export const presetQueries = {
  all: (token: string | null) =>
    queryOptions({
      queryKey: ['presets', 'all'] as const,
      queryFn: token ? () => fetchPresets(token) : skipToken,
    }),
}
