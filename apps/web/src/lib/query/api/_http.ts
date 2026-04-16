import { ApiError } from '../errors'

/**
 * Internal fetch helper for plugin-authenticated API routes.
 *
 * Every plugin-facing query/mutation pairs the bearer token with
 * `Content-Type: application/json` and rethrows non-ok responses as
 * `ApiError` (which the global query-client error handler recognizes).
 * Two previous copies in `api/presets.ts` and `api/preferences.ts` are
 * consolidated here (audit finding CLAUDE.md Fix M1 — TanStack Query
 * deferred list).
 *
 * The leading underscore in the filename signals "internal to the
 * api/ folder" — call sites should only import from sibling files.
 */
export async function authFetch(
  url: string,
  token: string,
  init?: RequestInit,
): Promise<unknown> {
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...init?.headers,
    },
  })
  if (!res.ok) {
    const body = await res.text()
    throw new ApiError(res.status, body)
  }
  return res.json()
}
