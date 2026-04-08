//! Windows IPC backend: MIDI SysEx via LoopMIDI virtual port.
//!
//! FL Studio's Python subinterpreter blocks all _winapi pipe/socket creation
//! (CreateFile, CreateNamedPipe, CreatePipe all return INVALID_HANDLE with
//! err=0, meaning a Python-level security hook fires before any Win32 call).
//! MIDI messages are the only proven IPC mechanism for FL Studio scripts.
//!
//! ## Setup
//!
//! 1. Install LoopMIDI: https://www.tobias-erichsen.de/software/loopmidi.html
//! 2. Create TWO virtual ports: "Studio AI Cmd" and "Studio AI Resp".
//! 3. In FL Studio MIDI Settings → add a controller:
//!    - Input:  "Studio AI Cmd"   (FL receives plugin commands here)
//!    - Output: "Studio AI Resp"  (FL sends responses here)
//!    - Controller type: Studio AI
//! Note: WinMM only allows one exclusive MIDI output opener per port.
//!       Two ports are required so plugin and FL can each own one output.
//!
//! ## Protocol
//!
//! Command  (plugin → FL):   F0 7D 01 <UTF-8 JSON bytes> F7
//! Response (FL → plugin):   F0 7D 02 <UTF-8 JSON bytes> F7
//!
//! 0x7D = non-commercial / educational SysEx manufacturer ID.
//! Plugin ignores 01-tagged messages (its own echoes); FL script ignores 02.

use base64::{engine::general_purpose::STANDARD, Engine as _};
use midir::{MidiInput, MidiOutput, MidiOutputConnection};
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
static RELAY_LOCK: Mutex<()> = Mutex::new(());
static SETUP_LOCK: Mutex<()> = Mutex::new(());
static RESP_TX: OnceLock<Mutex<Option<mpsc::SyncSender<String>>>> = OnceLock::new();

// ─────────────────────── public API ───────────────────────

/// Open the "Studio AI" MIDI port and start the input listener thread.
/// Called once during plugin construction (renamed from setup_pipes to keep
/// the same interface as the Unix backend).
pub fn setup_pipes() -> io::Result<()> {
    // Reset initialized so retry is possible
    INITIALIZED.store(false, Ordering::SeqCst);
    RESP_TX.get_or_init(|| Mutex::new(None));

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
pub fn relay_to_fl(payload: &str) -> io::Result<String> {
    // Lazy-connect: try setup on every call until it succeeds
    if !INITIALIZED.load(Ordering::SeqCst) {
        let _setup = SETUP_LOCK.lock().unwrap();
        if !INITIALIZED.load(Ordering::SeqCst) {
            if let Err(e) = setup_pipes() {
                return Err(io::Error::new(
                    io::ErrorKind::NotConnected,
                    format!("MIDI IPC not available (is LoopMIDI running with 'Studio AI' port?): {}", e),
                ));
            }
        }
    }

    let _lock = RELAY_LOCK
        .lock()
        .map_err(|_| io::Error::new(io::ErrorKind::Other, "relay lock poisoned"))?;

    // Fresh one-shot response channel
    let (tx, rx) = mpsc::sync_channel::<String>(1);
    {
        let mutex = RESP_TX
            .get()
            .ok_or_else(|| io::Error::new(io::ErrorKind::NotConnected, "MIDI IPC not initialised"))?;
        *mutex.lock().unwrap() = Some(tx);
    }

    // Build SysEx: F0 7D 01 <base64(json)> F7
    // base64 ensures all payload bytes are <= 0x7F (MIDI SysEx safe).
    let encoded = STANDARD.encode(payload.as_bytes());
    let mut sysex = Vec::with_capacity(encoded.len() + 4);
    sysex.extend_from_slice(&[0xF0, MFR_ID, TAG_CMD]);
    sysex.extend_from_slice(encoded.as_bytes());
    sysex.push(0xF7);

    {
        let mut guard = OUTPUT
            .lock()
            .map_err(|_| io::Error::new(io::ErrorKind::Other, "MIDI output lock poisoned"))?;
        let conn = guard.as_mut().ok_or_else(|| {
            io::Error::new(io::ErrorKind::NotConnected, "MIDI output not connected")
        })?;
        conn.send(&sysex)
            .map_err(|e| io::Error::new(io::ErrorKind::Other, format!("MIDI send: {}", e)))?;
    }

    rx.recv_timeout(RELAY_TIMEOUT)
        .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "FL script response timeout (5 s)"))
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
    match std::str::from_utf8(&decoded) {
        Ok(json) => {
            if let Some(mutex) = RESP_TX.get() {
                if let Ok(guard) = mutex.lock() {
                    if let Some(tx) = guard.as_ref() {
                        let _ = tx.try_send(json.to_string());
                    }
                }
            }
        }
        Err(e) => log::warn!("Studio AI: response UTF-8 error: {}", e),
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
