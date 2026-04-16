import {
  QueryClient,
  QueryCache,
  MutationCache,
  isServer,
} from '@tanstack/react-query'
import { ApiError } from './errors'

function handle401() {
  if (typeof window !== 'undefined') {
    localStorage.removeItem('studio-ai-token')
    window.location.href = '/plugin'
  }
}

function makeQueryClient() {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error) => {
        if (error instanceof ApiError && error.status === 401) handle401()
      },
    }),
    mutationCache: new MutationCache({
      onError: (error) => {
        if (error instanceof ApiError && error.status === 401) handle401()
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 60 * 1000,
        // Plugin users tab between DAW and WebView constantly; refetching on
        // every focus change would hammer the relay for no perceivable
        // benefit (staleTime of 60s already covers normal interaction).
        // Dashboard queries (when added) can override per-query if they
        // need the live-feel of focus-based refresh. Audit: CLAUDE.md
        // deferred-fix M5.
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          if (error instanceof ApiError && error.status === 401) return false
          return failureCount < 3
        },
      },
    },
  })
}

let browserQueryClient: QueryClient | undefined

export function getQueryClient() {
  if (isServer) {
    return makeQueryClient()
  }
  if (!browserQueryClient) {
    browserQueryClient = makeQueryClient()
  }
  return browserQueryClient
}
