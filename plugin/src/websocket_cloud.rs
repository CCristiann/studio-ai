//! Thread A: Cloud WebSocket client.
//!
//! Connects to FastAPI relay service, authenticates with JWT,
//! receives action messages, relays them to FL Studio via pipe IPC,
//! and sends responses back.

use futures_util::{SinkExt, StreamExt};
use tokio::sync::mpsc;
use tokio::time::{Duration, interval, sleep};
use tokio_tungstenite::{
    connect_async,
    tungstenite::{
        client::IntoClientRequest,
        http::HeaderValue,
        Message,
    },
};

use crate::pipe_ipc;
use crate::state::SharedState;

const HEARTBEAT_INTERVAL: Duration = Duration::from_secs(30);
const MAX_BACKOFF: Duration = Duration::from_secs(60);

pub async fn run(shared_state: SharedState) {
    let mut backoff = Duration::from_secs(1);

    loop {
        // Wait until we have a JWT token
        let (token, ws_url) = loop {
            let maybe = {
                let state = shared_state.lock().unwrap();
                state.jwt_token.as_ref().map(|t| (t.clone(), state.cloud_ws_url.clone()))
            };
            if let Some(pair) = maybe {
                break pair;
            }
            sleep(Duration::from_millis(500)).await;
        };

        log::info!("Connecting to cloud WebSocket: {}", ws_url);

        {
            let mut state = shared_state.lock().unwrap();
            state.cloud_connected = false;
            state.update_connection_state();
        }

        // Handshake auth: send the JWT in the Authorization header so the
        // server can reject before the upgrade completes (no DoS surface
        // from holding unauthenticated sockets). See ADR
        // 2026-04-15-ws-handshake-auth.
        let request = match (&ws_url).into_client_request() {
            Ok(mut req) => {
                match HeaderValue::from_str(&format!("Bearer {}", token)) {
                    Ok(value) => {
                        req.headers_mut().insert("Authorization", value);
                        req
                    }
                    Err(e) => {
                        log::error!("Invalid token for Authorization header: {}", e);
                        sleep(backoff).await;
                        backoff = (backoff * 2).min(MAX_BACKOFF);
                        continue;
                    }
                }
            }
            Err(e) => {
                log::error!("Failed to build WS request: {}", e);
                sleep(backoff).await;
                backoff = (backoff * 2).min(MAX_BACKOFF);
                continue;
            }
        };

        let ws_stream = match connect_async(request).await {
            Ok((stream, _)) => stream,
            Err(e) => {
                // 401 / 403 here = JWT rejected pre-accept by the relay.
                // Token-level errors won't recover by retrying — but transient
                // network errors will, so the standard backoff loop continues.
                log::error!("Cloud WS connection failed: {}", e);
                sleep(backoff).await;
                backoff = (backoff * 2).min(MAX_BACKOFF);
                continue;
            }
        };

        backoff = Duration::from_secs(1);

        let (mut write, mut read) = ws_stream.split();

        {
            let mut state = shared_state.lock().unwrap();
            state.cloud_connected = true;
            state.update_connection_state();
        }

        log::info!("Cloud WebSocket connected and authenticated");

        let (tx, mut rx) = mpsc::unbounded_channel::<String>();

        // Heartbeat task
        let heartbeat_tx = tx.clone();
        let heartbeat_handle = tokio::spawn(async move {
            let mut timer = interval(HEARTBEAT_INTERVAL);
            loop {
                timer.tick().await;
                let hb = serde_json::json!({
                    "id": uuid::Uuid::new_v4().to_string(),
                    "type": "heartbeat",
                    "payload": {
                        "timestamp": std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .unwrap()
                            .as_secs()
                    }
                });
                if heartbeat_tx.send(hb.to_string()).is_err() {
                    break;
                }
            }
        });

        // Send loop: forward outbound messages to WebSocket
        let send_handle = tokio::spawn(async move {
            while let Some(msg) = rx.recv().await {
                if write.send(Message::Text(msg)).await.is_err() {
                    break;
                }
            }
        });

        // Receive loop: handle incoming messages from cloud
        let response_tx = tx.clone();
        let recv_handle = tokio::spawn(async move {
            while let Some(Ok(msg)) = read.next().await {
                match msg {
                    Message::Text(text) => {
                        if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&text) {
                            let msg_type = parsed.get("type").and_then(|t| t.as_str());
                            match msg_type {
                                Some("action") => {
                                    log::info!("Received action from cloud, relaying to FL Studio");
                                    let tx = response_tx.clone();
                                    let action_text = text.clone();
                                    // Spawn relay task so we don't block the receive loop
                                    tokio::spawn(async move {
                                        let response = relay_action_to_fl(&action_text).await;
                                        if tx.send(response).is_err() {
                                            log::error!("Failed to send response to cloud WS");
                                        }
                                    });
                                }
                                Some("error") => {
                                    log::warn!("Error from cloud: {}", text);
                                }
                                _ => {
                                    log::debug!("Cloud message: {}", text);
                                }
                            }
                        }
                    }
                    Message::Close(_) => {
                        log::info!("Cloud WebSocket closed by server");
                        break;
                    }
                    _ => {}
                }
            }
        });

        tokio::select! {
            _ = send_handle => {},
            _ = recv_handle => {},
        }

        heartbeat_handle.abort();

        {
            let mut state = shared_state.lock().unwrap();
            state.cloud_connected = false;
            state.update_connection_state();
        }

        log::info!("Cloud WebSocket disconnected, reconnecting in {:?}", backoff);
        sleep(backoff).await;
        backoff = (backoff * 2).min(MAX_BACKOFF);
    }
}

/// Relay an action message to FL Studio via pipe IPC and build a response.
async fn relay_action_to_fl(action_json: &str) -> String {
    let parsed: serde_json::Value = match serde_json::from_str(action_json) {
        Ok(v) => v,
        Err(e) => {
            log::error!("Failed to parse action: {}", e);
            return make_error_response("unknown", "DAW_ERROR", &format!("Parse error: {}", e));
        }
    };

    let msg_id = parsed.get("id").and_then(|v| v.as_str()).unwrap_or("unknown");

    if parsed.get("payload").is_none() {
        return make_error_response(msg_id, "DAW_ERROR", "Missing payload in action");
    }

    // Build command for FL script with message ID for correlation
    let fl_command = serde_json::json!({
        "id": msg_id,
        "action": parsed["payload"].get("action").and_then(|a| a.as_str()).unwrap_or(""),
        "params": parsed["payload"].get("params").unwrap_or(&serde_json::Value::Object(Default::default())),
    });

    match pipe_ipc::relay_to_fl_async(fl_command.to_string()).await {
        Ok(response_str) => {
            // Parse FL script response and wrap in envelope
            match serde_json::from_str::<serde_json::Value>(&response_str) {
                Ok(fl_response) => {
                    let success = fl_response.get("success").and_then(|s| s.as_bool()).unwrap_or(false);
                    let response = serde_json::json!({
                        "id": msg_id,
                        "type": "response",
                        "payload": {
                            "success": success,
                            "data": fl_response.get("data").unwrap_or(&serde_json::Value::Null),
                        }
                    });
                    response.to_string()
                }
                Err(_) => {
                    // FL script returned non-JSON, wrap as-is
                    let response = serde_json::json!({
                        "id": msg_id,
                        "type": "response",
                        "payload": {
                            "success": true,
                            "data": response_str,
                        }
                    });
                    response.to_string()
                }
            }
        }
        Err(e) => {
            let code = match e.kind() {
                std::io::ErrorKind::TimedOut => "DAW_TIMEOUT",
                std::io::ErrorKind::BrokenPipe => "BRIDGE_DISCONNECTED",
                std::io::ErrorKind::NotConnected | std::io::ErrorKind::NotFound => "BRIDGE_DISCONNECTED",
                _ => "DAW_ERROR",
            };
            log::error!("MIDI IPC relay failed: {}", e);
            make_error_response(msg_id, code, &e.to_string())
        }
    }
}

fn make_error_response(id: &str, code: &str, message: &str) -> String {
    serde_json::json!({
        "id": id,
        "type": "error",
        "payload": {
            "code": code,
            "message": message,
        }
    })
    .to_string()
}
