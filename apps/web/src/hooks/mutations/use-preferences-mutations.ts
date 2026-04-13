import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  updatePreferences,
  UpdatePreferencesInput,
} from '@/lib/query/api/preferences'
import { usePluginToken } from '@/hooks/use-plugin-auth'

export function useUpdatePreferences() {
  const queryClient = useQueryClient()
  const { token } = usePluginToken()

  return useMutation({
    mutationFn: (data: UpdatePreferencesInput) => {
      if (!token) throw new Error('Not authenticated')
      return updatePreferences(token, data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['preferences'] })
    },
  })
}
