/**
 * Core message envelope used across ALL connections in Studio AI.
 * Cloud WebSocket, local bridge WebSocket, and IPC all use this format.
 */

export type MessageType = "action" | "response" | "heartbeat" | "error" | "state";

export interface MessageEnvelope<T = unknown> {
  id: string;
  type: MessageType;
  payload: T;
}

export interface ActionPayload {
  action: string;
  params: Record<string, unknown>;
}

export interface ResponsePayload {
  success: boolean;
  data: unknown;
}

export interface HeartbeatPayload {
  timestamp: number;
}

export interface ErrorPayload {
  code: ErrorCode;
  message: string;
}

export interface StatePayload {
  bpm: number;
  tracks: TrackInfo[];
  project_name: string;
}

export interface TrackInfo {
  index: number;
  name: string;
  type: "audio" | "midi" | "automation";
  muted: boolean;
  solo: boolean;
  volume: number;
  pan: number;
}

export type ErrorCode =
  | "PLUGIN_OFFLINE"
  | "BRIDGE_DISCONNECTED"
  | "DAW_TIMEOUT"
  | "DAW_ERROR"
  | "RELAY_TIMEOUT";

export interface AuthPayload {
  token: string;
}

// Typed message constructors
export type ActionMessage = MessageEnvelope<ActionPayload>;
export type ResponseMessage = MessageEnvelope<ResponsePayload>;
export type HeartbeatMessage = MessageEnvelope<HeartbeatPayload>;
export type ErrorMessage = MessageEnvelope<ErrorPayload>;
export type StateMessage = MessageEnvelope<StatePayload>;
export type AuthMessage = MessageEnvelope<AuthPayload>;
