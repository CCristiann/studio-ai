# FL Studio IPC Two-Script Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `MMSYSERR_ALLOCATED` on Windows by splitting the FL Studio MIDI script into two controller entries (receive + respond), adding base64 payload encoding, and wiring the macOS pipe transport into `device_studio_ai.py`.

**Architecture:** The Rust plugin sends `TAG_CMD` SysEx to `Studio AI Cmd` port; `device_studio_ai_receive.py` (Controller 1, no output) dispatches the command and replies with `TAG_INTERNAL` SysEx via FL Studio's internal port-1 bus; `device_studio_ai_respond.py` (Controller 2, output=`Studio AI Resp`) re-tags it as `TAG_RESP` and emits it externally. All payloads are base64-encoded for MIDI 7-bit safety. On macOS, `device_studio_ai.py` uses fd 20/21 anonymous pipes (no MIDI at all).

**Tech Stack:** Rust (`midir`, `base64 = "0.22"`), Python 3.12 (FL Studio restricted environment — no sockets, no ctypes, no subprocess), LoopMIDI (Windows), `unittest` (Python stdlib).

**Spec:** `docs/superpowers/specs/2026-04-08-fl-studio-ipc-two-script-design.md`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `plugin/Cargo.toml` | Add `base64 = "0.22"` dependency |
| Modify | `plugin/src/pipe_ipc/windows.rs` | base64-encode outbound SysEx, base64-decode inbound |
| Create | `bridge/fl_studio/_protocol.py` | Shared SysEx encode/decode helpers (no FL API imports) |
| Create | `bridge/fl_studio/tests/test_protocol.py` | Unit tests for `_protocol.py` (stdlib only, runs outside FL) |
| Create | `bridge/fl_studio/device_studio_ai_receive.py` | Windows receive script — dispatches commands, sends TAG_INTERNAL |
| Create | `bridge/fl_studio/device_studio_ai_respond.py` | Windows respond script — relays TAG_INTERNAL → TAG_RESP |
| Modify | `bridge/fl_studio/device_studio_ai.py` | Add macOS pipe transport path (`_USE_PIPE` detection) |
| Modify | `scripts/install-fl-script.sh` | Copy new scripts; update setup instructions |

---

## Task 1: Add base64 to Cargo.toml and update windows.rs

**Files:**
- Modify: `plugin/Cargo.toml`
- Modify: `plugin/src/pipe_ipc/windows.rs`

### Step 1.1 — Write the failing test in windows.rs

Add this module at the bottom of `plugin/src/pipe_ipc/windows.rs` (before the closing brace if any, otherwise at end of file):

```rust
#[cfg(test)]
mod tests {
    use base64::{engine::general_purpose::STANDARD, Engine as _};

    const MFR_ID_TEST: u8 = 0x7D;
    const TAG_CMD_TEST: u8 = 0x01;

    #[test]
    fn test_sysex_encode_decode_roundtrip() {
        let payload = r#"{"id":"test","action":"set_bpm","params":{"bpm":160}}"#;

        // Encode path (what relay_to_fl will do)
        let encoded = STANDARD.encode(payload.as_bytes());
        let mut sysex = Vec::new();
        sysex.extend_from_slice(&[0xF0, MFR_ID_TEST, TAG_CMD_TEST]);
        sysex.extend_from_slice(encoded.as_bytes());
        sysex.push(0xF7);

        assert_eq!(sysex[0], 0xF0);
        assert_eq!(sysex[1], MFR_ID_TEST);
        assert_eq!(sysex[2], TAG_CMD_TEST);
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
        sysex.extend_from_slice(&[0xF0, MFR_ID_TEST, TAG_CMD_TEST]);
        sysex.extend_from_slice(encoded.as_bytes());
        sysex.push(0xF7);

        // F0 and F7 are MIDI status bytes — only the data bytes (indices 1..len-1)
        // must be < 0x80. Check the data portion only.
        for &b in &sysex[1..sysex.len() - 1] {
            assert!(b < 0x80, "byte {:#x} is not 7-bit safe", b);
        }
    }
}
```

- [ ] **Step 1.2 — Run tests to confirm they fail (base64 crate not yet added)**

```bash
cd plugin
cargo test 2>&1 | head -30
```

Expected: compile error mentioning `base64` not found.

- [ ] **Step 1.3 — Add base64 to Cargo.toml**

In `plugin/Cargo.toml`, add one line to `[dependencies]` (after `midir = "0.10"`):

```toml
base64 = "0.22"
```

- [ ] **Step 1.4 — Add use declaration and update relay_to_fl in windows.rs**

At the top of `plugin/src/pipe_ipc/windows.rs`, after the existing `use` lines, add:

```rust
use base64::{engine::general_purpose::STANDARD, Engine as _};
```

In `relay_to_fl`, replace the SysEx construction block (currently lines ~138–143):

```rust
    // Build SysEx: F0 7D 01 <json> F7
    let mut sysex = Vec::with_capacity(payload.len() + 4);
    sysex.extend_from_slice(&[0xF0, MFR_ID, TAG_CMD]);
    sysex.extend_from_slice(payload.as_bytes());
    sysex.push(0xF7);
```

Replace with:

```rust
    // Build SysEx: F0 7D 01 <base64(json)> F7
    // base64 ensures all payload bytes are <= 0x7F (MIDI SysEx safe).
    let encoded = STANDARD.encode(payload.as_bytes());
    let mut sysex = Vec::with_capacity(encoded.len() + 4);
    sysex.extend_from_slice(&[0xF0, MFR_ID, TAG_CMD]);
    sysex.extend_from_slice(encoded.as_bytes());
    sysex.push(0xF7);
```

- [ ] **Step 1.5 — Update on_sysex to base64-decode the response**

In `on_sysex`, replace the current body (lines ~188–207):

```rust
fn on_sysex(msg: &[u8]) {
    // Expected: F0 7D 02 <json bytes> F7
    if msg.len() < 5
        || msg[0] != 0xF0
        || msg[1] != MFR_ID
        || msg[2] != TAG_RESP
        || *msg.last().unwrap() != 0xF7
    {
        return;
    }
    let json_bytes = &msg[3..msg.len() - 1];
    if let Ok(json) = std::str::from_utf8(json_bytes) {
        if let Some(mutex) = RESP_TX.get() {
            if let Ok(guard) = mutex.lock() {
                if let Some(tx) = guard.as_ref() {
                    let _ = tx.try_send(json.to_string());
                }
            }
        }
    }
}
```

With:

```rust
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
```

- [ ] **Step 1.6 — Run tests to confirm they pass**

```bash
cd plugin
cargo test 2>&1
```

Expected output includes:
```
test tests::test_sysex_encode_decode_roundtrip ... ok
test tests::test_all_sysex_bytes_midi_safe ... ok
```

- [ ] **Step 1.7 — Verify plugin still compiles**

```bash
cd plugin
cargo build 2>&1 | tail -5
```

Expected: `Compiling studio-ai-plugin` ... `Finished`.

- [ ] **Step 1.8 — Commit**

```bash
cd plugin
git add Cargo.toml Cargo.lock src/pipe_ipc/windows.rs
git commit -m "feat(plugin/windows): base64-encode MIDI SysEx payloads

Fixes MMSYSERR_ALLOCATED by preparing the protocol for two-script
FL Studio architecture. base64 keeps all SysEx bytes <= 0x7F."
```

---

## Task 2: Create `_protocol.py` and unit tests

**Files:**
- Create: `bridge/fl_studio/_protocol.py`
- Create: `bridge/fl_studio/tests/__init__.py`
- Create: `bridge/fl_studio/tests/test_protocol.py`

- [ ] **Step 2.1 — Write the failing tests first**

Create `bridge/fl_studio/tests/__init__.py` (empty):

```python
```

Create `bridge/fl_studio/tests/test_protocol.py`:

```python
"""Unit tests for _protocol.py — runs outside FL Studio (stdlib only)."""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _protocol import (
    encode_sysex, decode_sysex,
    TAG_CMD, TAG_RESP, TAG_INTERNAL, MFR_ID,
)


class TestEncodeDecodeSysex(unittest.TestCase):

    def test_roundtrip_ascii_json(self):
        original = '{"id":"abc","action":"set_bpm","params":{"bpm":160}}'
        sysex = encode_sysex(TAG_CMD, original)
        tag, decoded = decode_sysex(sysex)
        self.assertEqual(tag, TAG_CMD)
        self.assertEqual(decoded, original)

    def test_roundtrip_unicode_track_name(self):
        original = '{"name":"K\u00fcche \u2014 Drums"}'
        sysex = encode_sysex(TAG_CMD, original)
        tag, decoded = decode_sysex(sysex)
        self.assertEqual(decoded, original)

    def test_header_structure(self):
        sysex = encode_sysex(TAG_CMD, "{}")
        self.assertEqual(sysex[0], 0xF0)
        self.assertEqual(sysex[1], MFR_ID)
        self.assertEqual(sysex[2], TAG_CMD)
        self.assertEqual(sysex[-1], 0xF7)

    def test_all_payload_bytes_midi_safe(self):
        # Every byte between F0 and F7 must be < 0x80
        sysex = encode_sysex(TAG_CMD, '{"name":"K\u00fcche \u2014 test \u00e9"}')
        data_bytes = sysex[1:-1]  # exclude F0, F7
        for i, b in enumerate(data_bytes):
            self.assertLess(b, 0x80, f"byte[{i+1}] = {b:#x} exceeds 0x7F")

    def test_tag_internal(self):
        sysex = encode_sysex(TAG_INTERNAL, '{"success":true}')
        tag, decoded = decode_sysex(sysex)
        self.assertEqual(tag, TAG_INTERNAL)
        self.assertEqual(decoded, '{"success":true}')

    def test_tag_resp(self):
        sysex = encode_sysex(TAG_RESP, '{"success":true,"data":{}}')
        tag, decoded = decode_sysex(sysex)
        self.assertEqual(tag, TAG_RESP)

    def test_rejects_too_short(self):
        with self.assertRaises(ValueError):
            decode_sysex(bytes([0xF0, MFR_ID]))

    def test_rejects_wrong_mfr_id(self):
        with self.assertRaises(ValueError):
            decode_sysex(bytes([0xF0, 0x41, TAG_CMD, 0x00, 0xF7]))

    def test_rejects_missing_f7(self):
        with self.assertRaises(ValueError):
            decode_sysex(bytes([0xF0, MFR_ID, TAG_CMD, 0x00, 0x00]))

    def test_empty_payload_roundtrip(self):
        sysex = encode_sysex(TAG_CMD, "{}")
        tag, decoded = decode_sysex(sysex)
        self.assertEqual(decoded, "{}")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2.2 — Run tests to confirm they fail**

```bash
python bridge/fl_studio/tests/test_protocol.py 2>&1
```

Expected: `ModuleNotFoundError: No module named '_protocol'`

- [ ] **Step 2.3 — Create `_protocol.py`**

Create `bridge/fl_studio/_protocol.py`:

```python
"""SysEx protocol helpers for Studio AI.

Shared by device_studio_ai_receive.py and device_studio_ai_respond.py.
No FL Studio API imports — this module can be imported and tested
outside FL Studio.

Wire format:
    F0  7D  [TAG]  [base64(UTF-8 JSON)]  F7

Tags:
    TAG_CMD      = 0x01  — plugin → receive script (external, via Studio AI Cmd)
    TAG_RESP     = 0x02  — respond script → plugin (external, via Studio AI Resp)
    TAG_INTERNAL = 0x03  — receive script → respond script (FL internal port bus)
"""

import base64

MFR_ID       = 0x7D
TAG_CMD      = 0x01
TAG_RESP     = 0x02
TAG_INTERNAL = 0x03

_SYSEX_START = 0xF0
_SYSEX_END   = 0xF7


def encode_sysex(tag, json_str):
    """Return a SysEx bytestring for the given tag and JSON payload.

    All bytes between F0 and F7 are guaranteed < 0x80 (MIDI-safe).

    Args:
        tag:      One of TAG_CMD, TAG_RESP, TAG_INTERNAL.
        json_str: A valid JSON string (str).

    Returns:
        bytes — complete SysEx message including F0 / F7 framing.
    """
    encoded = base64.b64encode(json_str.encode("utf-8"))  # pure ASCII bytes
    return bytes([_SYSEX_START, MFR_ID, tag]) + encoded + bytes([_SYSEX_END])


def decode_sysex(data):
    """Parse a SysEx message and return (tag, json_str).

    Args:
        data: bytes — the raw SysEx bytes including F0 / F7 framing.

    Returns:
        (tag: int, json_str: str)

    Raises:
        ValueError — if the message is malformed or not from Studio AI.
    """
    if not data or len(data) < 5:
        raise ValueError("SysEx too short: " + str(len(data) if data else 0))
    if data[0] != _SYSEX_START or data[-1] != _SYSEX_END:
        raise ValueError("Missing F0/F7 framing")
    if data[1] != MFR_ID:
        raise ValueError("Wrong manufacturer ID: " + hex(data[1]))
    tag = data[2]
    try:
        json_str = base64.b64decode(data[3:-1]).decode("utf-8")
    except Exception as e:
        raise ValueError("Payload decode error: " + str(e))
    return tag, json_str
```

- [ ] **Step 2.4 — Run tests to confirm they all pass**

```bash
python bridge/fl_studio/tests/test_protocol.py -v 2>&1
```

Expected:
```
test_all_payload_bytes_midi_safe ... ok
test_empty_payload_roundtrip ... ok
test_header_structure ... ok
test_rejects_missing_f7 ... ok
test_rejects_too_short ... ok
test_rejects_wrong_mfr_id ... ok
test_roundtrip_ascii_json ... ok
test_roundtrip_unicode_track_name ... ok
test_tag_internal ... ok
test_tag_resp ... ok
----------------------------------------------------------------------
Ran 10 tests in 0.00xs

OK
```

- [ ] **Step 2.5 — Commit**

```bash
git add bridge/fl_studio/_protocol.py bridge/fl_studio/tests/
git commit -m "feat(bridge): add SysEx protocol helpers with unit tests

_protocol.py provides encode_sysex/decode_sysex with base64 encoding.
All payload bytes guaranteed < 0x80 (MIDI 7-bit safe)."
```

---

## Task 3: Create `device_studio_ai_receive.py`

**Files:**
- Create: `bridge/fl_studio/device_studio_ai_receive.py`

This script replaces `device_studio_ai.py` for Windows. It handles `TAG_CMD` messages, dispatches to handlers, and re-emits results as `TAG_INTERNAL` via FL Studio's internal port bus.

> **Known limitation:** `get_project_state` on large projects (many channels/tracks) may produce JSON > 700 bytes raw. After base64 inflation this can exceed WinMM's ~1000-byte SysEx buffer. Chunking is deferred — for now, the script will silently fail on large state responses. Track this as a follow-up.

- [ ] **Step 3.1 — Create the file**

Create `bridge/fl_studio/device_studio_ai_receive.py`:

```python
# name=Studio AI Receive
# url=https://studioai.app

"""FL Studio MIDI Script — Studio AI Receive (Windows only).

Controller entry in FL Studio MIDI Settings:
  Input:  Studio AI Cmd
  Output: (none — do not set)
  Port:   1
  Type:   Studio AI Receive

Receives TAG_CMD SysEx from the Rust plugin, dispatches to handlers,
and emits TAG_INTERNAL responses via FL Studio's internal port-1 bus.
The respond script (device_studio_ai_respond.py) on the same port
picks up TAG_INTERNAL and forwards it externally as TAG_RESP.

Protocol:
  Inbound:  F0 7D 01 <base64(JSON)> F7  (TAG_CMD from plugin)
  Outbound: F0 7D 03 <base64(JSON)> F7  (TAG_INTERNAL to respond script)
"""

import json
import device

from _protocol import encode_sysex, decode_sysex, TAG_CMD, TAG_INTERNAL
from handlers_organize import ORGANIZE_HANDLERS


# ──────────────────── FL Studio callbacks ────────────────────

def OnInit():
    _log("Studio AI Receive ready")


def OnDeInit():
    _log("Studio AI Receive shutting down")


def OnIdle():
    pass


def OnMidiMsg(event):
    pass


def OnSysEx(event):
    try:
        raw = bytes(event.sysex) if hasattr(event, "sysex") and event.sysex else None
    except Exception as e:
        _log("sysex read error: " + str(e))
        return

    event.handled = True

    if raw is None or len(raw) < 5:
        return

    try:
        tag, json_str = decode_sysex(raw)
    except ValueError as e:
        _log("decode error: " + str(e))
        return

    if tag != TAG_CMD:
        return  # ignore TAG_RESP and TAG_INTERNAL echoes on this port

    _handle_command(json_str)


# ──────────────────── Command dispatch ────────────────────

def _handle_command(json_str):
    try:
        cmd = json.loads(json_str)
    except (ValueError, TypeError) as e:
        _log("Invalid JSON: " + str(e))
        return

    cmd_id = cmd.get("id", "unknown")
    action = cmd.get("action", "")
    params = cmd.get("params", {})

    handler = _HANDLERS.get(action)
    if handler is None:
        _send_internal(cmd_id, False, {"error": "Unknown action: " + action})
        return

    try:
        result = handler(params)
        _send_internal(cmd_id, True, result)
    except Exception as e:
        _log("Action '" + action + "' failed: " + str(e))
        _send_internal(cmd_id, False, {"error": str(e)})


def _send_internal(cmd_id, success, data=None):
    payload = json.dumps({"id": cmd_id, "success": success, "data": data})
    try:
        device.midiOutSysex(encode_sysex(TAG_INTERNAL, payload))
    except Exception as e:
        _log("midiOutSysex (internal) failed: " + str(e))


# ──────────────────── Handlers ────────────────────

def _cmd_set_bpm(params):
    import general
    import midi
    bpm = params.get("bpm")
    if bpm is None or not (10 <= bpm <= 999):
        raise ValueError("BPM must be 10-999, got: " + str(bpm))
    general.processRECEvent(
        midi.REC_Tempo,
        round(float(bpm) * 1000),
        midi.REC_Control | midi.REC_UpdateControl,
    )
    return {"bpm": bpm}


def _cmd_get_state(params):
    import general
    import mixer
    import transport as fl_transport

    bpm = float(mixer.getCurrentTempo()) / 1000.0
    project_name = general.getProjectTitle() or "Untitled"
    is_playing = fl_transport.isPlaying()

    tracks = []
    for i in range(mixer.trackCount()):
        name = mixer.getTrackName(i)
        if not name or name.startswith("Insert "):
            continue
        tracks.append({
            "index": i,
            "name": name,
            "muted": bool(mixer.isTrackMuted(i)),
            "solo": bool(mixer.isTrackSolo(i)),
            "volume": round(mixer.getTrackVolume(i), 3),
            "pan": round(mixer.getTrackPan(i), 3),
        })

    return {
        "bpm": bpm,
        "project_name": project_name,
        "playing": bool(is_playing),
        "tracks": tracks,
    }


def _cmd_add_track(params):
    import channels
    name = params.get("name", "New Track")
    idx = channels.channelCount()
    channels.setChannelName(idx, name)
    return {"index": idx, "name": name}


def _cmd_play(params):
    import transport as fl_transport
    fl_transport.start()
    return {"playing": True}


def _cmd_stop(params):
    import transport as fl_transport
    fl_transport.stop()
    return {"playing": False}


def _cmd_record(params):
    import transport as fl_transport
    fl_transport.record()
    return {"recording": True}


def _cmd_set_track_volume(params):
    import mixer
    index = int(params.get("index", 0))
    volume = float(params.get("volume", 0.8))
    mixer.setTrackVolume(index, volume)
    return {"index": index, "volume": volume}


def _cmd_set_track_pan(params):
    import mixer
    index = int(params.get("index", 0))
    pan = float(params.get("pan", 0.0))
    mixer.setTrackPan(index, pan)
    return {"index": index, "pan": pan}


def _cmd_set_track_mute(params):
    import mixer
    index = int(params.get("index", 0))
    mixer.muteTrack(index)
    return {"index": index, "muted": bool(mixer.isTrackMuted(index))}


def _cmd_set_track_solo(params):
    import mixer
    index = int(params.get("index", 0))
    mixer.soloTrack(index)
    return {"index": index, "solo": bool(mixer.isTrackSolo(index))}


def _cmd_rename_track(params):
    import mixer
    index = int(params.get("index", 0))
    name = params.get("name", "")
    mixer.setTrackName(index, name)
    return {"index": index, "name": name}


# ──────────────────── Handler registry ────────────────────

_HANDLERS = {
    "set_bpm":           _cmd_set_bpm,
    "get_state":         _cmd_get_state,
    "add_track":         _cmd_add_track,
    "play":              _cmd_play,
    "stop":              _cmd_stop,
    "record":            _cmd_record,
    "set_track_volume":  _cmd_set_track_volume,
    "set_track_pan":     _cmd_set_track_pan,
    "set_track_mute":    _cmd_set_track_mute,
    "set_track_solo":    _cmd_set_track_solo,
    "rename_track":      _cmd_rename_track,
    **ORGANIZE_HANDLERS,
}


# ──────────────────── Utility ────────────────────

def _log(msg):
    print("[Studio AI Receive] " + str(msg))
```

- [ ] **Step 3.2 — Verify the file runs syntactically outside FL Studio**

This confirms no syntax errors before deploying to FL Studio:

```bash
python -c "import ast; ast.parse(open('bridge/fl_studio/device_studio_ai_receive.py').read()); print('Syntax OK')"
```

Expected: `Syntax OK`

- [ ] **Step 3.3 — Commit**

```bash
git add bridge/fl_studio/device_studio_ai_receive.py
git commit -m "feat(bridge): add device_studio_ai_receive.py for Windows two-script IPC"
```

---

## Task 4: Create `device_studio_ai_respond.py`

**Files:**
- Create: `bridge/fl_studio/device_studio_ai_respond.py`

This script is ~40 lines with zero business logic. It receives `TAG_INTERNAL` on FL Studio's port-1 internal bus and emits `TAG_RESP` externally on the `Studio AI Resp` LoopMIDI port.

- [ ] **Step 4.1 — Create the file**

Create `bridge/fl_studio/device_studio_ai_respond.py`:

```python
# name=Studio AI Respond
# url=https://studioai.app

"""FL Studio MIDI Script — Studio AI Respond (Windows only).

Controller entry in FL Studio MIDI Settings:
  Input:  Studio AI Cmd
  Output: Studio AI Resp
  Port:   1   ← must match device_studio_ai_receive.py
  Type:   Studio AI Respond

Receives TAG_INTERNAL SysEx from device_studio_ai_receive.py via
FL Studio's internal port-1 bus and re-emits it as TAG_RESP on the
Studio AI Resp LoopMIDI port so the Rust plugin can receive it.

No business logic lives here — this script is a pure relay.

Protocol:
  Inbound:  F0 7D 03 <base64(JSON)> F7  (TAG_INTERNAL from receive script)
  Outbound: F0 7D 02 <base64(JSON)> F7  (TAG_RESP to plugin via Studio AI Resp)
"""

import device

from _protocol import encode_sysex, decode_sysex, TAG_INTERNAL, TAG_RESP


# ──────────────────── FL Studio callbacks ────────────────────

def OnInit():
    _log("Studio AI Respond ready — output: Studio AI Resp")


def OnDeInit():
    _log("Studio AI Respond shutting down")


def OnIdle():
    pass


def OnMidiMsg(event):
    pass


def OnSysEx(event):
    try:
        raw = bytes(event.sysex) if hasattr(event, "sysex") and event.sysex else None
    except Exception as e:
        _log("sysex read error: " + str(e))
        return

    event.handled = True

    if raw is None or len(raw) < 5:
        return

    try:
        tag, json_str = decode_sysex(raw)
    except ValueError:
        return  # silently ignore malformed or non-Studio-AI SysEx

    if tag != TAG_INTERNAL:
        return  # ignore TAG_CMD from plugin, ignore TAG_RESP echoes

    try:
        device.midiOutSysex(encode_sysex(TAG_RESP, json_str))
    except Exception as e:
        _log("midiOutSysex (resp) failed: " + str(e))


# ──────────────────── Utility ────────────────────

def _log(msg):
    print("[Studio AI Respond] " + str(msg))
```

- [ ] **Step 4.2 — Syntax check**

```bash
python -c "import ast; ast.parse(open('bridge/fl_studio/device_studio_ai_respond.py').read()); print('Syntax OK')"
```

Expected: `Syntax OK`

- [ ] **Step 4.3 — Commit**

```bash
git add bridge/fl_studio/device_studio_ai_respond.py
git commit -m "feat(bridge): add device_studio_ai_respond.py — TAG_INTERNAL to TAG_RESP relay"
```

---

## Task 5: Wire macOS pipe transport in `device_studio_ai.py`

**Files:**
- Modify: `bridge/fl_studio/device_studio_ai.py`

On macOS the Rust plugin (a VST loaded inside FL Studio's process) creates anonymous pipes on fds 20/21 before FL Studio loads MIDI scripts. `ipc_transport.py`'s Unix backend detects these via `os.fstat(20)` and `os.fstat(21)`. This task wires that transport into `device_studio_ai.py` so macOS uses pipes instead of MIDI SysEx.

This file is **not used on Windows**. The receive/respond scripts are used there.

- [ ] **Step 5.1 — Add pipe detection imports at the top of device_studio_ai.py**

After the existing `import json` and `import device` lines, add:

```python
import sys

try:
    from ipc_transport import transport as _transport
    _USE_PIPE = sys.platform != "win32" and _transport.try_connect()
except Exception:
    _USE_PIPE = False

_pipe_buf = b""  # accumulate partial line-delimited reads from fd 20
```

- [ ] **Step 5.2 — Modify OnIdle to poll pipes when available**

Replace the existing `OnIdle` function:

```python
def OnIdle():
    pass
```

With:

```python
def OnIdle():
    if not _USE_PIPE:
        return
    global _pipe_buf
    chunk = _transport.read_available()
    if not chunk:
        return
    _pipe_buf += chunk
    # Commands are newline-delimited JSON strings
    while b"\n" in _pipe_buf:
        line, _pipe_buf = _pipe_buf.split(b"\n", 1)
        line = line.strip()
        if line:
            _handle_pipe_command(line.decode("utf-8", errors="replace"))
```

- [ ] **Step 5.3 — Add pipe command dispatcher and response sender**

Add these two functions after the existing `_handle_command` function in `device_studio_ai.py`:

```python
def _handle_pipe_command(json_str):
    """Dispatch a command received via pipe (macOS) and write response."""
    try:
        cmd = json.loads(json_str)
    except (ValueError, TypeError) as e:
        _log("Invalid JSON (pipe): " + str(e))
        return

    cmd_id = cmd.get("id", "unknown")
    action = cmd.get("action", "")
    params = cmd.get("params", {})

    handler = _HANDLERS.get(action)
    if handler is None:
        _send_pipe_response(cmd_id, False, {"error": "Unknown action: " + action})
        return

    try:
        result = handler(params)
        _send_pipe_response(cmd_id, True, result)
    except Exception as e:
        _log("Action '" + action + "' failed (pipe): " + str(e))
        _send_pipe_response(cmd_id, False, {"error": str(e)})


def _send_pipe_response(cmd_id, success, data=None):
    """Write a newline-delimited JSON response to the pipe (fd 21)."""
    payload = json.dumps({"id": cmd_id, "success": success, "data": data}) + "\n"
    try:
        _transport.write_response(payload.encode("utf-8"))
    except Exception as e:
        _log("pipe write failed: " + str(e))
```

- [ ] **Step 5.4 — Gate OnSysEx to skip when pipes are active**

In `device_studio_ai.py`, at the top of the existing `OnSysEx` function, add an early return:

```python
def OnSysEx(event):
    if _USE_PIPE:
        event.handled = True
        return  # pipe transport is active; SysEx is not used on macOS
    # ... rest of existing OnSysEx body unchanged ...
```

- [ ] **Step 5.5 — Syntax check**

```bash
python -c "import ast; ast.parse(open('bridge/fl_studio/device_studio_ai.py').read()); print('Syntax OK')"
```

Expected: `Syntax OK`

- [ ] **Step 5.6 — Commit**

```bash
git add bridge/fl_studio/device_studio_ai.py
git commit -m "feat(bridge): wire macOS pipe transport into device_studio_ai.py

_USE_PIPE auto-detects fd 20/21 on macOS. OnIdle polls for commands
over pipe; OnSysEx is bypassed when pipes are active."
```

---

## Task 6: Update `install-fl-script.sh`

**Files:**
- Modify: `scripts/install-fl-script.sh`

- [ ] **Step 6.1 — Add new source variables and copy commands**

In `install-fl-script.sh`, after the existing source variable declarations (after `TRANSPORT_SRC=...`), add:

```bash
PROTOCOL_SRC="$ROOT_DIR/bridge/fl_studio/_protocol.py"
RECEIVE_SRC="$ROOT_DIR/bridge/fl_studio/device_studio_ai_receive.py"
RESPOND_SRC="$ROOT_DIR/bridge/fl_studio/device_studio_ai_respond.py"
```

After the existing source file checks, add checks for the new files:

```bash
if [ ! -f "$PROTOCOL_SRC" ]; then
    echo -e "${RED}Protocol module not found: $PROTOCOL_SRC${NC}"
    exit 1
fi
if [ ! -f "$RECEIVE_SRC" ]; then
    echo -e "${RED}Receive script not found: $RECEIVE_SRC${NC}"
    exit 1
fi
if [ ! -f "$RESPOND_SRC" ]; then
    echo -e "${RED}Respond script not found: $RESPOND_SRC${NC}"
    exit 1
fi
```

After the existing `cp` commands, add:

```bash
cp "$PROTOCOL_SRC" "$DEST_DIR/_protocol.py"
cp "$RECEIVE_SRC"  "$DEST_DIR/device_studio_ai_receive.py"
cp "$RESPOND_SRC"  "$DEST_DIR/device_studio_ai_respond.py"
```

- [ ] **Step 6.2 — Replace the post-install instructions block**

Replace the entire "Next steps" echo block with this platform-aware version:

```bash
echo -e "${GREEN}FL Studio MIDI scripts installed to:${NC}"
echo "  $DEST_DIR/"
echo ""

if [[ "$OSTYPE" == "darwin"* ]]; then
    echo -e "${YELLOW}macOS setup:${NC}"
    echo "  1. Open FL Studio"
    echo "  2. Options → MIDI Settings"
    echo "  3. Add one controller entry:"
    echo "     Input:           any IAC Driver bus"
    echo "     Output:          any IAC Driver bus"
    echo "     Port:            1"
    echo "     Controller type: Studio AI"
    echo "  4. Enable (green button)"
    echo ""
    echo "  Data flows over anonymous pipes (no MIDI required for IPC)."
else
    echo -e "${YELLOW}Windows setup (LoopMIDI required):${NC}"
    echo "  1. Install LoopMIDI: https://www.tobias-erichsen.de/software/loopmidi.html"
    echo "  2. Create two virtual ports named exactly:"
    echo "       Studio AI Cmd"
    echo "       Studio AI Resp"
    echo "  3. Open FL Studio → Options → MIDI Settings"
    echo "  4. Add TWO controller entries:"
    echo ""
    echo "     Entry 1 (receive):"
    echo "       Input:           Studio AI Cmd"
    echo "       Output:          (leave empty / not set)"
    echo "       Port:            1"
    echo "       Controller type: Studio AI Receive"
    echo ""
    echo "     Entry 2 (respond):"
    echo "       Input:           Studio AI Cmd"
    echo "       Output:          Studio AI Resp"
    echo "       Port:            1   ← must match Entry 1"
    echo "       Controller type: Studio AI Respond"
    echo ""
    echo "  5. Enable both entries (green button on each)"
    echo ""
    echo "  Both entries must use Port=1."
fi

echo -e "${GREEN}Done!${NC}"
```

- [ ] **Step 6.3 — Run the install script and verify output**

```bash
bash scripts/install-fl-script.sh
```

Expected: no errors, shows platform-correct setup instructions, lists all files copied.

- [ ] **Step 6.4 — Commit**

```bash
git add scripts/install-fl-script.sh
git commit -m "chore(install): copy new bridge scripts and show platform-specific setup"
```

---

## Task 7: Integration Test

No automated test can reach FL Studio from outside — use this manual checklist.

### Pre-conditions

- [ ] LoopMIDI is running with ports `Studio AI Cmd` and `Studio AI Resp` (verify in LoopMIDI's port list)
- [ ] Install script ran successfully: `bash scripts/install-fl-script.sh`
- [ ] Plugin was built: `cd plugin && cargo build`

### FL Studio Setup Verification

- [ ] Open FL Studio → Options → MIDI Settings
- [ ] Confirm Entry 1: Input=`Studio AI Cmd`, Output=(none), Port=1, Type=`Studio AI Receive`, enabled (green)
- [ ] Confirm Entry 2: Input=`Studio AI Cmd`, Output=`Studio AI Resp`, Port=1, Type=`Studio AI Respond`, enabled (green)
- [ ] Open the FL Studio Script Output panel (View → Script Output or F12)
- [ ] Verify you see: `[Studio AI Receive] Studio AI Receive ready`
- [ ] Verify you see: `[Studio AI Respond] Studio AI Respond ready — output: Studio AI Resp`

### Functional Tests

- [ ] Open the Studio AI plugin in FL Studio (load as VST3)
- [ ] In the plugin chat, type: `set bpm to 120`
  - Expected: BPM changes to 120 in FL Studio's toolbar
  - Expected: No `MMSYSERR_ALLOCATED` error in the response
  - Expected plugin log: `Studio AI MIDI IPC ready`

- [ ] Type: `set bpm to 160`
  - Expected: BPM changes to 160

- [ ] Type: `play`
  - Expected: FL Studio starts playing

- [ ] Type: `stop`
  - Expected: FL Studio stops

- [ ] Type: `get state`
  - Expected: JSON with bpm, project_name, playing, tracks

### If TAG_INTERNAL routing fails (fallback test)

If the respond script's `OnSysEx` never fires (no `[Studio AI Respond]` logs after sending a command):

FL Studio's internal port-1 bus routing may not work without an explicit Output on Controller 1. Add a **third LoopMIDI port** `Studio AI Internal` and reconfigure:

| Entry | Input | Output | Port | Type |
|-------|-------|--------|------|------|
| 1 | Studio AI Cmd | Studio AI Internal | 1 | Studio AI Receive |
| 2 | Studio AI Internal | Studio AI Resp | 2 | Studio AI Respond |

No code changes needed — the scripts use `device.midiOutSysex()` regardless of what port is configured as Output; FL Studio routes based on the controller Output field.

- [ ] If fallback needed: update FL Studio MIDI settings as above and re-test

### Commit after integration success

```bash
git add -A
git commit -m "chore: integration verified — two-script MIDI IPC working on Windows"
```
