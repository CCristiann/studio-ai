# name=Studio AI
# url=https://studioai.app

"""FL Studio MIDI Script for Studio AI.

Communicates with the Studio AI VST3 plugin via MIDI SysEx messages over a
LoopMIDI virtual port named "Studio AI".

Setup (Windows)
---------------
1. Install LoopMIDI and create TWO virtual ports:
     - "Studio AI Cmd"   (plugin -> FL commands)
     - "Studio AI Resp"  (FL -> plugin responses)
2. In FL Studio: Options -> MIDI Settings.
   Input row:
     - Device:          Studio AI Cmd
     - Controller type: Studio AI
     - Port:            1
     - Enabled:         yes
   Output row:
     - Device:          Studio AI Resp
     - Port:            1   (MUST match the input Port number)
     - Enabled:         yes
   Only the Input row has a controller-type field. FL routes
   device.midiOutSysex() from this script to "Studio AI Resp"
   purely because both cables share Port number 1.
3. Options -> General settings -> enable "Run in background" so
   the script keeps responding when FL loses focus.

Setup (macOS)
-------------
Uses the ipc_transport pipe backend; no MIDI routing needed.

Protocol
--------
Command  (plugin → FL):  F0 7D 01 <UTF-8 JSON> F7
Response (FL → plugin):  F0 7D 02 <UTF-8 JSON> F7

JSON envelope:
  Command:  {"id": "<uuid>", "action": "set_bpm", "params": {"bpm": 160}}
  Response: {"id": "<uuid>", "success": true, "data": {"bpm": 160}}
"""

import json
import sys
import device

from _protocol import encode_sysex, decode_sysex, TAG_CMD, TAG_RESP
from handlers_organize import ORGANIZE_HANDLERS

try:
    from ipc_transport import transport as _transport
    _USE_PIPE = sys.platform != "win32" and _transport.try_connect()
except Exception:
    _USE_PIPE = False

_pipe_buf = b""  # accumulate partial line-delimited reads from fd 20


# ──────────────────── FL Studio callbacks ────────────────────

def OnInit():
    _log("Studio AI bridge ready (MIDI SysEx transport)")


def OnDeInit():
    _log("Studio AI bridge shutting down")


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


def OnMidiMsg(event):
    pass


def OnSysEx(event):
    """Called by FL Studio for incoming SysEx messages."""
    if _USE_PIPE:
        event.handled = True
        return  # pipe transport is active; SysEx is not used on macOS
    _log("OnSysEx called has_sysex=" + str(hasattr(event, "sysex")))
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
        return

    _handle_command(json_str)


# ──────────────────── Command handling ────────────────────

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
        _send_error(cmd_id, "Unknown action: " + action)
        return

    try:
        result = handler(params)
        _send_response(cmd_id, True, result)
    except Exception as e:
        _log("Action '" + action + "' failed: " + str(e))
        _send_error(cmd_id, str(e))


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


def _send_response(cmd_id, success, data=None):
    payload = json.dumps({"id": cmd_id, "success": success, "data": data})
    try:
        device.midiOutSysex(encode_sysex(TAG_RESP, payload))
    except Exception as e:
        _log("midiOutSysex failed: " + str(e))


def _send_error(cmd_id, message):
    _send_response(cmd_id, False, {"error": message})


# ──────────────────── FL Studio action handlers ────────────────────

def _cmd_set_bpm(params):
    import general
    import midi
    bpm = params.get("bpm")
    if bpm is None or not (10 <= bpm <= 999):
        raise ValueError("BPM must be 10–999, got: " + str(bpm))
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
    # FL Studio's Python SDK has no addChannel() API — channelCount() returns
    # the count, and index == count is out of range until a new channel is
    # added through the UI. Fail loudly instead of silently corrupting state.
    raise ValueError(
        "add_track is not supported: FL Studio's Python SDK has no addChannel() API. "
        "Add channels manually in the Channel Rack."
    )


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
    muted = bool(params.get("muted", True))
    # muteTrack is a toggle — only call it if the current state differs
    if bool(mixer.isTrackMuted(index)) != muted:
        mixer.muteTrack(index)
    return {"index": index, "muted": bool(mixer.isTrackMuted(index))}


def _cmd_set_track_solo(params):
    import mixer
    index = int(params.get("index", 0))
    solo = bool(params.get("solo", True))
    # soloTrack is a toggle — only call it if the current state differs
    if bool(mixer.isTrackSolo(index)) != solo:
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
    "set_bpm": _cmd_set_bpm,
    "get_state": _cmd_get_state,
    "get_project_state": _cmd_get_state,
    "add_track": _cmd_add_track,
    "play": _cmd_play,
    "stop": _cmd_stop,
    "record": _cmd_record,
    "set_track_volume": _cmd_set_track_volume,
    "set_track_pan": _cmd_set_track_pan,
    "set_track_mute": _cmd_set_track_mute,
    "set_track_solo": _cmd_set_track_solo,
    "rename_track": _cmd_rename_track,
    **ORGANIZE_HANDLERS,
}


# ──────────────────── Utility ────────────────────

def _log(msg):
    print("[Studio AI] " + str(msg))
