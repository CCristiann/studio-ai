//! Windows IPC backend: MIDI SysEx via LoopMIDI virtual ports.
//!
//! FL Studio's Python subinterpreter blocks all _winapi pipe/socket creation,
//! so MIDI SysEx is the only proven IPC mechanism for FL Studio scripts.
//!
//! ## Architecture
//!
//! One FL Studio script (`device_studio_ai.py`) owns one Port number
//! (Port 1 by convention). Two loopMIDI cables share that Port number:
//!
//!   Plugin OUT -> "Studio AI Cmd"  -> FL Input  (Port 1, Studio AI script)
//!   Plugin IN  <- "Studio AI Resp" <- FL Output (Port 1, no script field)
//!
//! FL routes `device.midiOutSysex()` from the script to "Studio AI Resp"
//! purely because both rows share Port number 1 in MIDI Settings. This is
//! the only correct shape — FL attaches scripts to Inputs only; there is
//! no "output script" slot.
//!
//! ## Setup
//!
//! 1. Install LoopMIDI: https://www.tobias-erichsen.de/software/loopmidi.html
//! 2. Create TWO virtual ports: "Studio AI Cmd" and "Studio AI Resp".
//! 3. In FL Studio MIDI Settings:
//!    - Input row:  device "Studio AI Cmd",  type Studio AI, Port 1, enabled.
//!    - Output row: device "Studio AI Resp", Port 1, enabled.
//!    Both Port numbers MUST match.
//!
//! ## Protocol
//!
//! Command  (plugin → FL):   F0 7D 01 <base64(UTF-8 JSON)> F7
//! Response (FL → plugin):   F0 7D 02 <base64(UTF-8 JSON)> F7
//!
//! 0x7D = non-commercial / educational SysEx manufacturer ID.
//! Base64 keeps every payload byte <= 0x7F (MIDI SysEx safe).
//! Requests and responses are correlated via the `id` field in the JSON.

use base64::{engine::general_purpose::STANDARD, Engine as _};
use midir::{MidiInput, MidiOutput, MidiOutputConnection};
use std::collections::HashMap;
use std::io;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    mpsc, Mutex, OnceLock,
};
use std::time::Duration;

const MFR_ID: u8 = 0x7D;
const TAG_CMD: u8 = 0x01;
const TAG_RESP: u8 = 0x02;
/// Plugin opens this as MIDI OUTPUT to send commands to FL Studio.
/// FL Studio opens this as its MIDI INPUT device.
const PORT_CMD: &str = "Studio AI Cmd";
/// FL Studio opens this as its MIDI OUTPUT device to send responses.
/// Plugin opens this as MIDI INPUT to receive responses.
const PORT_RESP: &str = "Studio AI Resp";
const RELAY_TIMEOUT: Duration = Duration::from_secs(5);

static INITIALIZED: AtomicBool = AtomicBool::new(false);
static OUTPUT: Mutex<Option<MidiOutputConnection>> = Mutex::new(None);
static SETUP_LOCK: Mutex<()> = Mutex::new(());
/// Per-request response channels keyed by command id. The MIDI input thread
/// looks up the matching sender in `on_sysex` and delivers the JSON payload.
static PENDING: OnceLock<Mutex<HashMap<String, mpsc::SyncSender<String>>>> = OnceLock::new();

fn pending() -> &'static Mutex<HashMap<String, mpsc::SyncSender<String>>> {
    PENDING.get_or_init(|| Mutex::new(HashMap::new()))
}

// ─────────────────────── public API ───────────────────────

/// Open the "Studio AI" MIDI port and start the input listener thread.
/// Called once during plugin construction (renamed from setup_pipes to keep
/// the same interface as the Unix backend).
pub fn setup_pipes() -> io::Result<()> {
    // Reset initialized so retry is possible
    INITIALIZED.store(false, Ordering::SeqCst);
    let _ = pending(); // force init

    let midi_out = MidiOutput::new("Studio AI")
        .map_err(|e| io::Error::new(io::ErrorKind::Other, e.to_string()))?;

    let out_ports = midi_out.ports();
    let out_names: Vec<String> = out_ports
        .iter()
        .map(|p| midi_out.port_name(p).unwrap_or_default())
        .collect();
    log::info!("Studio AI: available MIDI output ports: {:?}", out_names);

    let out_port = out_ports
        .iter()
        .find(|p| midi_out.port_name(p).unwrap_or_default().contains(PORT_CMD))
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::NotFound,
                format!(
                    "MIDI output port '{}' not found. Available: {:?}. \
                     Create it in LoopMIDI.",
                    PORT_CMD, out_names
                ),
            )
        })?;

    let conn = midi_out
        .connect(out_port, "studio-ai-cmd-out")
        .map_err(|e| io::Error::new(io::ErrorKind::Other, e.to_string()))?;

    *OUTPUT.lock().unwrap() = Some(conn);

    std::thread::Builder::new()
        .name("studio-ai-midi-in".into())
        .spawn(|| {
            if let Err(e) = run_midi_input() {
                log::error!("Studio AI MIDI input error: {}", e);
            }
        })
        .map_err(|e| io::Error::new(io::ErrorKind::Other, e))?;

    INITIALIZED.store(true, Ordering::SeqCst);
    log::info!("Studio AI MIDI IPC ready (cmd='{}', resp='{}')", PORT_CMD, PORT_RESP);
    Ok(())
}

pub fn is_initialized() -> bool {
    INITIALIZED.load(Ordering::SeqCst)
}

/// Send a JSON command to FL Studio and wait up to 5 s for the response.
///
/// Response transport: the FL Studio script calls `device.midiOutSysex(...)`,
/// which FL routes to "Studio AI Resp" (same Port number as the input cable).
/// The MIDI input thread in this module parses the SysEx, extracts the
/// command id, and delivers the JSON to the matching waiter in `PENDING`.
pub fn relay_to_fl(payload: &str) -> io::Result<String> {
    // Lazy-connect: try setup on every call until it succeeds
    if !INITIALIZED.load(Ordering::SeqCst) {
        let _setup = SETUP_LOCK.lock().unwrap();
        if !INITIALIZED.load(Ordering::SeqCst) {
            if let Err(e) = setup_pipes() {
                return Err(io::Error::new(
                    io::ErrorKind::NotConnected,
                    format!("MIDI IPC not available (is LoopMIDI running with 'Studio AI Cmd' and 'Studio AI Resp' ports?): {}", e),
                ));
            }
        }
    }

    // Extract cmd_id from the payload so we can correlate the response.
    let cmd_id = serde_json::from_str::<serde_json::Value>(payload)
        .ok()
        .and_then(|v| v.get("id").and_then(|id| id.as_str()).map(|s| s.to_string()))
        .ok_or_else(|| {
            io::Error::new(io::ErrorKind::InvalidInput, "command payload missing 'id' field")
        })?;

    // Register a response channel for this id BEFORE sending, so we cannot
    // miss a fast response that arrives between send and register.
    let (tx, rx) = mpsc::sync_channel::<String>(1);
    {
        let mut map = pending()
            .lock()
            .map_err(|_| io::Error::new(io::ErrorKind::Other, "pending map poisoned"))?;
        map.insert(cmd_id.clone(), tx);
    }

    // Build SysEx: F0 7D 01 <base64(json)> F7. base64 keeps bytes <= 0x7F.
    let encoded = STANDARD.encode(payload.as_bytes());
    let mut sysex = Vec::with_capacity(encoded.len() + 4);
    sysex.extend_from_slice(&[0xF0, MFR_ID, TAG_CMD]);
    sysex.extend_from_slice(encoded.as_bytes());
    sysex.push(0xF7);

    let send_result = {
        let mut guard = OUTPUT
            .lock()
            .map_err(|_| io::Error::new(io::ErrorKind::Other, "MIDI output lock poisoned"))?;
        let conn = guard.as_mut().ok_or_else(|| {
            io::Error::new(io::ErrorKind::NotConnected, "MIDI output not connected")
        })?;
        conn.send(&sysex)
            .map_err(|e| io::Error::new(io::ErrorKind::Other, format!("MIDI send: {}", e)))
    };
    if let Err(e) = send_result {
        let _ = pending().lock().map(|mut m| m.remove(&cmd_id));
        return Err(e);
    }

    // Wait for the MIDI input thread to deliver the response JSON.
    match rx.recv_timeout(RELAY_TIMEOUT) {
        Ok(json) => Ok(json),
        Err(mpsc::RecvTimeoutError::Timeout) => {
            let _ = pending().lock().map(|mut m| m.remove(&cmd_id));
            Err(io::Error::new(
                io::ErrorKind::TimedOut,
                "FL script response timeout (5 s)",
            ))
        }
        Err(mpsc::RecvTimeoutError::Disconnected) => {
            let _ = pending().lock().map(|mut m| m.remove(&cmd_id));
            Err(io::Error::new(
                io::ErrorKind::BrokenPipe,
                "response channel disconnected",
            ))
        }
    }
}

// ─────────────────────── MIDI input thread ───────────────────────

fn run_midi_input() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let midi_in = MidiInput::new("Studio AI In")?;
    let ports = midi_in.ports();
    let in_names: Vec<String> = ports
        .iter()
        .map(|p| midi_in.port_name(p).unwrap_or_default())
        .collect();
    log::info!("Studio AI: available MIDI input ports: {:?}", in_names);
    let port = ports
        .iter()
        .find(|p| {
            midi_in
                .port_name(p)
                .unwrap_or_default()
                .contains(PORT_RESP)
        })
        .ok_or_else(|| format!("MIDI input port '{}' not found. Available: {:?}. Create it in LoopMIDI.", PORT_RESP, in_names))?;

    // _conn must stay alive — dropping it closes the port
    let _conn = midi_in.connect(port, "studio-ai-in", |_ts, msg, _| on_sysex(msg), ())?;

    loop {
        std::thread::sleep(Duration::from_secs(60));
    }
}

fn on_sysex(msg: &[u8]) {
    // Expected: F0 7D 02 <base64(json)> F7
    if msg.len() < 5
        || msg[0] != 0xF0
        || msg[1] != MFR_ID
        || msg[2] != TAG_RESP
        || *msg.last().unwrap() != 0xF7
    {
        return;
    }
    let b64_slice = &msg[3..msg.len() - 1];
    let decoded = match STANDARD.decode(b64_slice) {
        Ok(b) => b,
        Err(e) => {
            log::warn!("Studio AI: base64 decode error: {}", e);
            return;
        }
    };
    let json = match std::str::from_utf8(&decoded) {
        Ok(s) => s,
        Err(e) => {
            log::warn!("Studio AI: response UTF-8 error: {}", e);
            return;
        }
    };

    // Extract the command id to route the response to its waiter.
    let cmd_id = match serde_json::from_str::<serde_json::Value>(json)
        .ok()
        .and_then(|v| v.get("id").and_then(|id| id.as_str()).map(|s| s.to_string()))
    {
        Some(id) => id,
        None => {
            log::warn!("Studio AI: response missing 'id' field: {}", json);
            return;
        }
    };

    let tx_opt = pending().lock().ok().and_then(|mut m| m.remove(&cmd_id));
    match tx_opt {
        Some(tx) => {
            let _ = tx.try_send(json.to_string());
        }
        None => log::warn!("Studio AI: unmatched response id {}", cmd_id),
    }
}

#[cfg(test)]
mod tests {
    use super::{MFR_ID, TAG_CMD};
    use base64::{engine::general_purpose::STANDARD, Engine as _};

    #[test]
    fn test_sysex_encode_decode_roundtrip() {
        let payload = r#"{"id":"test","action":"set_bpm","params":{"bpm":160}}"#;

        // Encode path (what relay_to_fl will do)
        let encoded = STANDARD.encode(payload.as_bytes());
        let mut sysex = Vec::new();
        sysex.extend_from_slice(&[0xF0, MFR_ID, TAG_CMD]);
        sysex.extend_from_slice(encoded.as_bytes());
        sysex.push(0xF7);

        assert_eq!(sysex[0], 0xF0);
        assert_eq!(sysex[1], MFR_ID);
        assert_eq!(sysex[2], TAG_CMD);
        assert_eq!(*sysex.last().unwrap(), 0xF7);

        // Decode path (what on_sysex will do)
        let b64_slice = &sysex[3..sysex.len() - 1];
        let decoded_bytes = STANDARD.decode(b64_slice).expect("base64 decode");
        let decoded_str = std::str::from_utf8(&decoded_bytes).expect("utf8");
        assert_eq!(decoded_str, payload);
    }

    #[test]
    fn test_all_sysex_bytes_midi_safe() {
        // Unicode in track names (e.g. "Küche") must not produce bytes >= 0x80
        let payload = r#"{"name":"K\u00fcche \u2014 test"}"#;
        let encoded = STANDARD.encode(payload.as_bytes());
        let mut sysex = Vec::new();
        sysex.extend_from_slice(&[0xF0, MFR_ID, TAG_CMD]);
        sysex.extend_from_slice(encoded.as_bytes());
        sysex.push(0xF7);

        // Check only the data bytes between F0 and F7
        for &b in &sysex[1..sysex.len() - 1] {
            assert!(b < 0x80, "byte {:#x} is not 7-bit safe", b);
        }
    }
}
