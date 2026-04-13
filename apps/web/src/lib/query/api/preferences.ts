import { ApiError } from '../errors'

export interface Preferences {
  onboarding_completed: boolean
}

export interface UpdatePreferencesInput {
  onboarding_completed?: boolean
}

const BASE = '/api/plugin/preferences'

async function authFetch(url: string, token: string, init?: RequestInit) {
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

export async function fetchPreferences(token: string): Promise<Preferences> {
  const data = await authFetch(BASE, token)
  return data.preferences
}

export async function updatePreferences(
  token: string,
  input: UpdatePreferencesInput,
): Promise<Preferences> {
  const data = await authFetch(BASE, token, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
  return data.preferences
}
