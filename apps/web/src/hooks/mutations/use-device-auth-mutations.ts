import { useMutation } from '@tanstack/react-query'
import { initiateDeviceFlow } from '@/lib/query/api/auth'

export function useInitiateDeviceFlow() {
  return useMutation({
    mutationFn: () => initiateDeviceFlow(),
  })
}
