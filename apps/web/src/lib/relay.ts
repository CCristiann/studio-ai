/**
 * HTTP client for relaying actions to plugins via FastAPI.
 */

export interface RelayRequest {
  action: string;
  params: Record<string, unknown>;
}

export interface RelayResponse {
  id: string;
  success: boolean;
  data: unknown;
  error?: string;
  code?: string;
}

const FASTAPI_URL = process.env.FASTAPI_URL ?? "http://localhost:8000";
const API_KEY = process.env.FASTAPI_INTERNAL_API_KEY ?? "";

export async function relay(
  userId: string,
  action: string,
  params: Record<string, unknown> = {}
): Promise<RelayResponse> {
  const url = `${FASTAPI_URL}/relay/${userId}`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
    },
    body: JSON.stringify({ action, params }),
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    const detail = errorBody.detail ?? {};
    const code = detail.code ?? "UNKNOWN_ERROR";
    const message = detail.message ?? `Relay failed with status ${response.status}`;

    throw new RelayError(code, message, response.status);
  }

  return response.json();
}

export class RelayError extends Error {
  code: string;
  statusCode: number;

  constructor(code: string, message: string, statusCode: number) {
    super(message);
    this.name = "RelayError";
    this.code = code;
    this.statusCode = statusCode;
  }
}
