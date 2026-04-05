//! Shared plugin state and connection status tracking.

use std::sync::{Arc, Mutex};

/// Connection state machine matching the architecture spec.
#[derive(Debug, Clone, PartialEq)]
pub enum ConnectionState {
    Offline,
    Connecting,
    CloudConnected,
    FullyConnected,
}

#[derive(Debug)]
pub struct PluginState {
    pub connection_state: ConnectionState,
    pub jwt_token: Option<String>,
    pub cloud_ws_url: String,
    pub bridge_ws_url: String,
    pub cloud_connected: bool,
    pub bridge_connected: bool,
}

/// Read cloud WS URL from config file, compile-time env, or default.
fn resolve_cloud_ws_url() -> String {
    // 1. Config file: ~/.config/studio-ai/config.json
    if let Some(home) = dirs::home_dir() {
        let config_path = home.join(".config/studio-ai/config.json");
        if let Ok(contents) = std::fs::read_to_string(&config_path) {
            if let Ok(json) = serde_json::from_str::<serde_json::Value>(&contents) {
                if let Some(url) = json.get("cloud_ws_url").and_then(|v| v.as_str()) {
                    return url.to_string();
                }
            }
        }
    }
    // 2. Compile-time env override
    if let Some(url) = option_env!("STUDIOAI_WS_URL") {
        return url.to_string();
    }
    // 3. Default: localhost for dev
    String::from("ws://localhost:8000/ws")
}

impl PluginState {
    pub fn new() -> Self {
        Self {
            connection_state: ConnectionState::Offline,
            jwt_token: None,
            cloud_ws_url: resolve_cloud_ws_url(),
            bridge_ws_url: String::from("ws://localhost:57120"),
            cloud_connected: false,
            bridge_connected: false,
        }
    }

    pub fn update_connection_state(&mut self) {
        self.connection_state = match (self.cloud_connected, self.bridge_connected) {
            (true, true) => ConnectionState::FullyConnected,
            (true, false) => ConnectionState::CloudConnected,
            (false, _) if self.jwt_token.is_some() => ConnectionState::Connecting,
            _ => ConnectionState::Offline,
        };
    }

    pub fn set_token(&mut self, token: String) {
        self.jwt_token = Some(token);
        self.update_connection_state();
    }
}

pub type SharedState = Arc<Mutex<PluginState>>;

pub fn create_shared_state() -> SharedState {
    Arc::new(Mutex::new(PluginState::new()))
}
