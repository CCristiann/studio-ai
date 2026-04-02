//! Thread A: Cloud WebSocket client.

use futures_util::{SinkExt, StreamExt};
use tokio::sync::mpsc;
use tokio::time::{Duration, interval, sleep};
use tokio_tungstenite::{connect_async, tungstenite::Message};

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

        let ws_stream = match connect_async(&ws_url).await {
            Ok((stream, _)) => stream,
            Err(e) => {
                log::error!("Cloud WS connection failed: {}", e);
                sleep(backoff).await;
                backoff = (backoff * 2).min(MAX_BACKOFF);
                continue;
            }
        };

        backoff = Duration::from_secs(1);

        let (mut write, mut read) = ws_stream.split();

        // Send auth message
        let auth_msg = serde_json::json!({
            "type": "auth",
            "payload": { "token": token }
        });
        if let Err(e) = write.send(Message::Text(auth_msg.to_string())).await {
            log::error!("Failed to send auth: {}", e);
            continue;
        }

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

        // Send loop
        let send_handle = tokio::spawn(async move {
            while let Some(msg) = rx.recv().await {
                if write.send(Message::Text(msg)).await.is_err() {
                    break;
                }
            }
        });

        // Receive loop
        let recv_state = shared_state.clone();
        let recv_handle = tokio::spawn(async move {
            let _ = recv_state; // held for potential future use
            while let Some(Ok(msg)) = read.next().await {
                match msg {
                    Message::Text(text) => {
                        if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(&text) {
                            let msg_type = parsed.get("type").and_then(|t| t.as_str());
                            match msg_type {
                                Some("action") => {
                                    log::info!("Received action from cloud: {}", text);
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
