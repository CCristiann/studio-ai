//! Thread B: Local bridge WebSocket client.

use futures_util::{SinkExt, StreamExt};
use tokio::sync::mpsc;
use tokio::time::{Duration, sleep};
use tokio_tungstenite::{connect_async, tungstenite::Message};

use crate::state::SharedState;

const RETRY_INTERVAL: Duration = Duration::from_secs(2);

fn read_bridge_token() -> Option<String> {
    let path = bridge_token_path()?;
    std::fs::read_to_string(&path).ok().map(|s| s.trim().to_string())
}

fn bridge_token_path() -> Option<std::path::PathBuf> {
    #[cfg(target_os = "macos")]
    {
        dirs::home_dir().map(|h| h.join(".config/studio-ai/bridge.token"))
    }
    #[cfg(target_os = "windows")]
    {
        dirs::config_dir().map(|c| c.join("studio-ai/bridge.token"))
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        dirs::home_dir().map(|h| h.join(".config/studio-ai/bridge.token"))
    }
}

pub async fn run(shared_state: SharedState) {
    loop {
        let ws_url = {
            let state = shared_state.lock().unwrap();
            state.bridge_ws_url.clone()
        };

        let bridge_token = match read_bridge_token() {
            Some(token) if !token.is_empty() => token,
            _ => {
                log::warn!("Bridge token not found, retrying in {:?}", RETRY_INTERVAL);
                sleep(RETRY_INTERVAL).await;
                continue;
            }
        };

        log::info!("Connecting to bridge WebSocket: {}", ws_url);

        let ws_stream = match connect_async(&ws_url).await {
            Ok((stream, _)) => stream,
            Err(e) => {
                log::debug!("Bridge WS connection failed: {}", e);
                sleep(RETRY_INTERVAL).await;
                continue;
            }
        };

        let (mut write, mut read) = ws_stream.split();

        let auth_msg = serde_json::json!({
            "type": "auth",
            "payload": { "token": bridge_token }
        });
        if let Err(e) = write.send(Message::Text(auth_msg.to_string())).await {
            log::error!("Failed to send bridge auth: {}", e);
            sleep(RETRY_INTERVAL).await;
            continue;
        }

        {
            let mut state = shared_state.lock().unwrap();
            state.bridge_connected = true;
            state.update_connection_state();
        }

        log::info!("Bridge WebSocket connected and authenticated");

        let (_tx, mut rx) = mpsc::unbounded_channel::<String>();

        let send_handle = tokio::spawn(async move {
            while let Some(msg) = rx.recv().await {
                if write.send(Message::Text(msg)).await.is_err() {
                    break;
                }
            }
        });

        let recv_state = shared_state.clone();
        let recv_handle = tokio::spawn(async move {
            while let Some(Ok(msg)) = read.next().await {
                match msg {
                    Message::Text(text) => {
                        if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&text) {
                            let msg_type = parsed.get("type").and_then(|t| t.as_str());
                            match msg_type {
                                Some("response") => {
                                    log::info!("Bridge response: {}", text);
                                }
                                Some("error") => {
                                    log::warn!("Bridge error: {}", text);
                                }
                                Some("state") => {
                                    log::info!("DAW state update received");
                                }
                                _ => {
                                    log::debug!("Bridge message: {}", text);
                                }
                            }
                        }
                    }
                    Message::Close(_) => {
                        log::info!("Bridge WebSocket closed");
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

        {
            let mut state = shared_state.lock().unwrap();
            state.bridge_connected = false;
            state.update_connection_state();
        }

        log::info!("Bridge WebSocket disconnected, retrying in {:?}", RETRY_INTERVAL);
        sleep(RETRY_INTERVAL).await;
    }
}
