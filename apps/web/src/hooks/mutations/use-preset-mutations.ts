import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  createPreset,
  updatePreset,
  deletePreset,
  CreatePresetInput,
} from '@/lib/query/api/presets'
import { usePluginToken } from '@/hooks/use-plugin-auth'

function useRequiredToken() {
  const { token } = usePluginToken()
  return () => {
    if (!token) throw new Error('Not authenticated')
    return token
  }
}

export function useCreatePreset() {
  const queryClient = useQueryClient()
  const getToken = useRequiredToken()

  return useMutation({
    mutationFn: (data: CreatePresetInput) => createPreset(getToken(), data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['presets'] })
    },
  })
}

export function useUpdatePreset() {
  const queryClient = useQueryClient()
  const getToken = useRequiredToken()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CreatePresetInput> }) =>
      updatePreset(getToken(), id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['presets'] })
    },
  })
}

export function useDeletePreset() {
  const queryClient = useQueryClient()
  const getToken = useRequiredToken()

  return useMutation({
    mutationFn: (id: string) => deletePreset(getToken(), id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['presets'] })
    },
  })
}
