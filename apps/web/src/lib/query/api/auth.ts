import { ApiError } from '../errors'

export interface DeviceFlowSession {
  session_id: string
  device_code: string
  user_code: string
  expires_in: number
}

export interface DeviceTokenResponse {
  status: 'pending' | 'complete' | 'expired'
  token?: string
}

export async function validateToken(token: string): Promise<{ valid: true }> {
  const res = await fetch('/api/auth/plugin/validate', {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) {
    const body = await res.text()
    throw new ApiError(res.status, body)
  }
  const data = await res.json()
  // Soft revocation: server may return 200 with { valid: false }.
  // Normalize to the same 401 path so the global handler runs.
  if (!data.valid) {
    throw new ApiError(401, JSON.stringify(data))
  }
  return data
}

export async function initiateDeviceFlow(): Promise<DeviceFlowSession> {
  const res = await fetch('/api/auth/device', { method: 'POST' })
  if (!res.ok) {
    const body = await res.text()
    throw new ApiError(res.status, body)
  }
  return res.json()
}

export async function pollDeviceToken(
  sessionId: string,
  deviceCode: string,
): Promise<DeviceTokenResponse> {
  const res = await fetch('/api/auth/device/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, device_code: deviceCode }),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new ApiError(res.status, body)
  }
  return res.json()
}
