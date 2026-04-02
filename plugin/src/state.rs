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

impl PluginState {
    pub fn new() -> Self {
        Self {
            connection_state: ConnectionState::Offline,
            jwt_token: None,
            cloud_ws_url: String::from("wss://api.studioai.app/ws"),
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
