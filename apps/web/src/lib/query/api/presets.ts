import { authFetch } from './_http'

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

export async function fetchPresets(token: string): Promise<Preset[]> {
  const data = (await authFetch(BASE, token)) as { presets: Preset[] }
  return data.presets
}

export async function createPreset(
  token: string,
  input: CreatePresetInput,
): Promise<Preset> {
  const data = (await authFetch(BASE, token, {
    method: 'POST',
    body: JSON.stringify(input),
  })) as { preset: Preset }
  return data.preset
}

export async function updatePreset(
  token: string,
  id: string,
  input: Partial<CreatePresetInput>,
): Promise<Preset> {
  const data = (await authFetch(`${BASE}/${id}`, token, {
    method: 'PUT',
    body: JSON.stringify(input),
  })) as { preset: Preset }
  return data.preset
}

export async function deletePreset(
  token: string,
  id: string,
): Promise<{ success: boolean }> {
  return (await authFetch(`${BASE}/${id}`, token, {
    method: 'DELETE',
  })) as { success: boolean }
}
