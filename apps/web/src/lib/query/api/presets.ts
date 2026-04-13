import { ApiError } from '../errors'

export interface Preset {
  id: string
  name: string
  description: string | null
  prompt: string
  created_at: string
  updated_at: string
}

export interface CreatePresetInput {
  name: string
  description?: string | null
  prompt: string
}

const BASE = '/api/plugin/presets'

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

export async function fetchPresets(token: string): Promise<Preset[]> {
  const data = await authFetch(BASE, token)
  return data.presets
}

export async function createPreset(
  token: string,
  input: CreatePresetInput,
): Promise<Preset> {
  const data = await authFetch(BASE, token, {
    method: 'POST',
    body: JSON.stringify(input),
  })
  return data.preset
}

export async function updatePreset(
  token: string,
  id: string,
  input: Partial<CreatePresetInput>,
): Promise<Preset> {
  const data = await authFetch(`${BASE}/${id}`, token, {
    method: 'PUT',
    body: JSON.stringify(input),
  })
  return data.preset
}

export async function deletePreset(
  token: string,
  id: string,
): Promise<{ success: boolean }> {
  return authFetch(`${BASE}/${id}`, token, { method: 'DELETE' })
}
