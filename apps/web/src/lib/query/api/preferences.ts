import { authFetch } from './_http'

export interface Preferences {
  onboarding_completed: boolean
}

export interface UpdatePreferencesInput {
  onboarding_completed?: boolean
}

const BASE = '/api/plugin/preferences'

export async function fetchPreferences(token: string): Promise<Preferences> {
  const data = (await authFetch(BASE, token)) as { preferences: Preferences }
  return data.preferences
}

export async function updatePreferences(
  token: string,
  input: UpdatePreferencesInput,
): Promise<Preferences> {
  const data = (await authFetch(BASE, token, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })) as { preferences: Preferences }
  return data.preferences
}
