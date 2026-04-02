//! WebView <-> Rust IPC message handling.

use serde::{Deserialize, Serialize};
use crate::state::SharedState;

/// Messages received FROM the WebView.
#[derive(Debug, Deserialize)]
#[serde(tag = "type", content = "payload")]
pub enum IpcMessageFromWebView {
    #[serde(rename = "sendToken")]
    SendToken { token: String },

    #[serde(rename = "sendAction")]
    SendAction { action: String, params: serde_json::Value },
}

/// Messages sent TO the WebView.
#[derive(Debug, Serialize)]
#[serde(tag = "type", content = "payload")]
pub enum IpcMessageToWebView {
    #[serde(rename = "connectionStatus")]
    ConnectionStatus { state: String },

    #[serde(rename = "actionResult")]
    ActionResult {
        id: String,
        success: bool,
        data: serde_json::Value,
    },
}

/// Handle an IPC message from the WebView.
pub fn handle_ipc_message(
    raw: &str,
    shared_state: &SharedState,
    cloud_tx: &Option<tokio::sync::mpsc::UnboundedSender<String>>,
) {
    let message: IpcMessageFromWebView = match serde_json::from_str(raw) {
        Ok(msg) => msg,
        Err(e) => {
            log::warn!("Failed to parse IPC message: {}", e);
            return;
        }
    };

    match message {
        IpcMessageFromWebView::SendToken { token } => {
            log::info!("Received JWT from WebView");
            if let Ok(mut state) = shared_state.lock() {
                state.set_token(token.clone());
            }
            if let Some(tx) = cloud_tx {
                let auth_msg = serde_json::json!({
                    "type": "auth",
                    "payload": { "token": token }
                });
                let _ = tx.send(auth_msg.to_string());
            }
        }
        IpcMessageFromWebView::SendAction { action, params } => {
            log::info!("Received action from WebView: {}", action);
            if let Some(tx) = cloud_tx {
                let msg = serde_json::json!({
                    "id": uuid::Uuid::new_v4().to_string(),
                    "type": "action",
                    "payload": { "action": action, "params": params }
                });
                let _ = tx.send(msg.to_string());
            }
        }
    }
}

/// Create a JavaScript snippet to update connection status in the WebView.
pub fn connection_status_js(state: &str) -> String {
    format!(
        r#"if (window.__studioai__) {{ window.__studioai__.onConnectionStatus("{}"); }}"#,
        state
    )
}

/// Create a JavaScript snippet to deliver an action result to the WebView.
pub fn action_result_js(id: &str, success: bool, data: &serde_json::Value) -> String {
    format!(
        r#"if (window.__studioai__) {{ window.__studioai__.onActionResult({json}); }}"#,
        json = serde_json::json!({ "id": id, "success": success, "data": data })
    )
}
