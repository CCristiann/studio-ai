/**
 * DAW action types. Each action maps to a specific DAW API call
 * executed by the bridge script.
 */

export type DawActionType =
  | "set_bpm"
  | "get_state"
  | "add_track"
  | "remove_track"
  | "set_track_volume"
  | "set_track_pan"
  | "set_track_mute"
  | "set_track_solo"
  | "rename_track"
  | "play"
  | "stop"
  | "record";

export interface SetBpmAction {
  action: "set_bpm";
  params: {
    bpm: number;
  };
}

export interface GetStateAction {
  action: "get_state";
  params: Record<string, never>;
}

export interface AddTrackAction {
  action: "add_track";
  params: {
    name: string;
    type: "audio" | "midi";
  };
}

export interface RemoveTrackAction {
  action: "remove_track";
  params: {
    index: number;
  };
}

export interface SetTrackVolumeAction {
  action: "set_track_volume";
  params: {
    index: number;
    volume: number;
  };
}

export interface SetTrackPanAction {
  action: "set_track_pan";
  params: {
    index: number;
    pan: number;
  };
}

export interface SetTrackMuteAction {
  action: "set_track_mute";
  params: {
    index: number;
    muted: boolean;
  };
}

export interface SetTrackSoloAction {
  action: "set_track_solo";
  params: {
    index: number;
    solo: boolean;
  };
}

export interface RenameTrackAction {
  action: "rename_track";
  params: {
    index: number;
    name: string;
  };
}

export interface PlayAction {
  action: "play";
  params: Record<string, never>;
}

export interface StopAction {
  action: "stop";
  params: Record<string, never>;
}

export interface RecordAction {
  action: "record";
  params: Record<string, never>;
}

export type DawAction =
  | SetBpmAction
  | GetStateAction
  | AddTrackAction
  | RemoveTrackAction
  | SetTrackVolumeAction
  | SetTrackPanAction
  | SetTrackMuteAction
  | SetTrackSoloAction
  | RenameTrackAction
  | PlayAction
  | StopAction
  | RecordAction;

/**
 * Subscription plan types matching the database schema.
 */
export type SubscriptionPlan = "free" | "pro" | "studio";
export type SubscriptionStatus = "active" | "canceled" | "past_due";

/**
 * Connection state enum matching the Rust plugin's state machine.
 */
export type ConnectionState =
  | "offline"
  | "connecting"
  | "cloud_connected"
  | "fully_connected";

/**
 * WebSocket close codes used by FastAPI.
 */
export const WS_CLOSE_AUTH_FAILED = 4001;
export const WS_CLOSE_SUBSCRIPTION_EXPIRED = 4003;
