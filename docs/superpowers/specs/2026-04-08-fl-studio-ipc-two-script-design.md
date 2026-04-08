# FL Studio IPC: Two-Script MIDI (Windows) + Pipe (macOS)

**Date**: 2026-04-08  
**Status**: Approved  
**Scope**: Fix `MMSYSERR_ALLOCATED` on Windows without touching macOS pipe transport

---

## Problem

FL Studio's MIDI controller entry with both `Input=Studio AI Cmd` and `Output=Studio AI Resp` causes FL Studio to also open `Studio AI Cmd` as a MIDI output (internal MIDI thru). This blocks the Rust plugin from opening `Studio AI Cmd` as its own MIDI output, resulting in:

```
MMSYSERR_ALLOCATED: could not create Windows MM MIDI output port
```

The macOS pipe transport (fd 20/21 anonymous pipes, `unix.rs`) is unaffected and must not be changed.

---

## Root Cause

WinMM enforces exclusive MIDI output ownership per port. When FL Studio's single controller entry has both Input and Output configured, it opens the Input port (`Studio AI Cmd`) as midiOut internally. The Rust plugin's `midir` then fails with `MMSYSERR_ALLOCATED` trying to open the same port as midiOut.

---

## Solution: Two-Script Architecture

Split the single FL Studio script into two controller entries. The **receive** entry has no Output configured — FL never opens `Studio AI Cmd` as midiOut. FL Studio's internal port-number bus (scripts sharing Port=1) routes the relay message from the receive script to the respond script.

### Data Flow

```
Plugin ──midiOut──► [Studio AI Cmd] ──midiIn──► Controller 1 (receive.py, Port=1, Output=none)
                                                    │ device.midiOutSysex(TAG_INTERNAL)
                                                    │ (FL internal routing, same Port=1)
                                                    ▼
                                                Controller 2 (respond.py, Port=1, Output=Studio AI Resp)
                                                    │ device.midiOutSysex(TAG_RESP)
Plugin ◄──midiIn──  [Studio AI Resp] ◄──midiOut─── ┘
```

**FL Studio opens**: `midiIn(Studio AI Cmd)` + `midiOut(Studio AI Resp)` only.  
**Plugin opens**: `midiOut(Studio AI Cmd)` + `midiIn(Studio AI Resp)`.  
**No conflict.**

---

## Protocol

Base64-encode all JSON payloads. Raw UTF-8 is unsafe for MIDI SysEx because Unicode characters (e.g. track names) can exceed 0x7F.

```
TAG_CMD      = 0x01  Plugin → FL (receive script)
TAG_RESP     = 0x02  FL → Plugin (respond script)
TAG_INTERNAL = 0x03  receive script → respond script (FL internal bus)

Wire format:  F0  7D  [TAG]  [base64(JSON)]  F7
```

Message routing by tag:
- **receive.py** `OnSysEx`: accepts `TAG_CMD` only; ignores `TAG_RESP`, `TAG_INTERNAL`
- **respond.py** `OnSysEx`: accepts `TAG_INTERNAL` only; ignores `TAG_CMD`, `TAG_RESP`

Both scripts share Port=1 so FL Studio's internal bus delivers `device.midiOutSysex()` output to all scripts on that port before sending it to any external MIDI device.

> **Assumption**: FL Studio routes `device.midiOutSysex()` to all scripts on the same port number internally (confirmed by Flapi's architecture; unverified by direct testing). **Fallback**: if internal routing does not work, add a third LoopMIDI port `Studio AI Internal` — Controller 1 Output=`Studio AI Internal`, Controller 2 Input=`Studio AI Internal`. This adds one port but removes any dependency on undocumented FL Studio behavior.

---

## Components

### New: `bridge/fl_studio/device_studio_ai_receive.py`

Replaces `device_studio_ai.py` as the primary script on Windows.

- `OnInit`: log ready message
- `OnSysEx`: filter `TAG_CMD` → base64-decode → dispatch to handler → base64-encode result → emit `TAG_INTERNAL` via `device.midiOutSysex()`
- Contains all handlers (set_bpm, get_state, etc.)
- Imports `handlers_organize`
- Ignores all non-`TAG_CMD` SysEx

### New: `bridge/fl_studio/device_studio_ai_respond.py`

~30 lines. Zero business logic.

- `OnSysEx`: filter `TAG_INTERNAL` → re-tag as `TAG_RESP` → emit via `device.midiOutSysex()` (reaches `Studio AI Resp` via Port=1 Output config)

### Modified: `bridge/fl_studio/device_studio_ai.py`

Used by macOS only. Add `sys.platform` check at top to use `ipc_transport.py` pipe transport (fd 20/21) when available. MIDI SysEx path retained as fallback (single-script, no two-script split needed on macOS — IAC Driver allows multiple midiOut openers).

Platform detection logic:
```python
import sys
from ipc_transport import transport

_USE_PIPE = sys.platform != "win32" and transport.try_connect()
```

`transport.try_connect()` calls `os.fstat(20)` / `os.fstat(21)` to check if the pipe fds exist. The Rust plugin's `setup_pipes()` runs during plugin construction (VST load), which happens before FL Studio loads MIDI scripts — so the fds are guaranteed present when this module-level check executes on macOS.

If `_USE_PIPE` is True: `OnIdle` reads from transport, dispatches handlers, writes response via transport. No SysEx used.  
If `_USE_PIPE` is False: existing SysEx path unchanged (MIDI, for forward-compat or future macOS MIDI scenarios).

### Modified: `plugin/src/pipe_ipc/windows.rs`

- Add `base64` dependency (`base64 = "0.22"` in `Cargo.toml`)
- `relay_to_fl`: base64-encode `payload` bytes before embedding in SysEx
- `on_sysex`: base64-decode bytes `msg[3..msg.len()-1]` before forwarding as JSON string

No changes to `unix.rs`, `mod.rs`, `websocket_cloud.rs`, or `websocket_bridge.rs`.

### Modified: `scripts/install-fl-script.sh`

Copy two additional files:
- `device_studio_ai_receive.py`
- `device_studio_ai_respond.py`

Update post-install instructions to be platform-specific:
- **macOS**: single controller entry instructions (unchanged)
- **Windows**: two controller entries with correct port numbers

---

## FL Studio Setup

### Windows (LoopMIDI — 2 ports required)

Create two LoopMIDI ports: `Studio AI Cmd`, `Studio AI Resp`.

In FL Studio → Options → MIDI Settings:

| # | Input | Output | Port | Controller type |
|---|-------|--------|------|----------------|
| 1 | Studio AI Cmd | *(none / not set)* | 1 | Studio AI Receive |
| 2 | Studio AI Cmd | Studio AI Resp | 1 | Studio AI Respond |

Both entries must use **Port = 1** (same number) for FL Studio's internal bus routing to work.

### macOS (IAC Driver — no new ports needed)

IAC Driver is built-in. In FL Studio → Options → MIDI Settings, one controller entry:

| # | Input | Output | Port | Controller type |
|---|-------|--------|------|----------------|
| 1 | *(any IAC bus)* | *(any IAC bus)* | 1 | Studio AI |

Pipe transport (fd 20/21) carries all data; MIDI is only used to load the script.

---

## Platform Matrix

| Concern | macOS | Windows |
|---------|-------|---------|
| IPC transport | fd 20/21 anonymous pipes | MIDI SysEx |
| External tool required | None | LoopMIDI (2 ports) |
| FL Studio controller entries | 1 | 2 |
| Base64 encoding | Not applicable (pipe is binary-safe) | Required |
| Rust changes | None | base64 encode/decode in `windows.rs` |
| Python scripts changed | `device_studio_ai.py` (pipe wiring) | `receive.py` + `respond.py` (new) |

---

## Error Handling

- **Receive script**: any handler exception → emit `TAG_INTERNAL` error response `{"success": false, "data": {"error": "..."}}`; respond script relays it as `TAG_RESP` unchanged
- **Respond script**: if `device.midiOutSysex()` fails → log error; plugin will time out (5 s deadline already in `windows.rs`)
- **Plugin side**: existing `RELAY_TIMEOUT = Duration::from_secs(5)` and `TimedOut` error handling unchanged
- **Payload size**: SysEx messages must fit within WinMM's ~1000-byte buffer after base64 inflation (~33% overhead). For a 700-byte JSON payload, base64 output is ~933 bytes — within limit. Payloads larger than 700 bytes raw should be chunked (deferred: `get_state` responses with many tracks can exceed this; add chunking in a follow-up).

---

## Out of Scope

- macOS MIDI SysEx two-script split (not needed; IAC Driver is non-exclusive)
- Message chunking for large payloads (>700 bytes raw JSON) — deferred
- Auto-configuration of FL Studio MIDI settings
- Removing `ipc_transport.py` (kept; used by macOS pipe path)
