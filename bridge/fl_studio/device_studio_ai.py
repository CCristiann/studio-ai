# name=Studio AI
# url=https://studioai.app
# supportedDevices=Studio AI

"""FL Studio MIDI Script for Studio AI.

Communicates with the Rust VST3 plugin via a platform-abstracted IPC
transport. On Unix the transport uses anonymous pipes inherited on
fds 20/21; on Windows it uses named pipes discovered through a
rendezvous file. See `ipc_transport.py` for the gritty details.

Protocol (identical on both platforms):
  Command:  {"id": "uuid", "action": "set_bpm", "params": {"bpm": 160}}
  Response: {"id": "uuid", "success": true, "data": {"bpm": 160}}
"""

import json

from handlers_organize import ORGANIZE_HANDLERS
from ipc_transport import transport

# ── Module state ──
_cmd_buffer = b""
_init_check_counter = 0
_INIT_CHECK_INTERVAL = 50  # Retry connect every ~1s (OnIdle runs ~50Hz)


# ──────────────────── FL Studio callbacks ────────────────────

def OnInit():
    """Called when FL Studio loads this MIDI script."""
    if transport.try_connect():
        _log("Studio AI bridge ready")


def OnDeInit():
    """Called when FL Studio unloads this MIDI script."""
    _log("Studio AI bridge shutting down")


def OnIdle():
    """Called ~50Hz by FL Studio. Polls for commands."""
    global _cmd_buffer, _init_check_counter

    if not transport.is_ready():
        # Retry transport setup periodically until the plugin side is up.
        _init_check_counter += 1
        if _init_check_counter >= _INIT_CHECK_INTERVAL:
            _init_check_counter = 0
            if transport.try_connect():
                _log("Studio AI bridge ready")
        return

    chunk = transport.read_available()
    if not chunk:
        return

    _cmd_buffer += chunk

    # Process complete lines (newline-delimited JSON)
    while b"\n" in _cmd_buffer:
        line, _cmd_buffer = _cmd_buffer.split(b"\n", 1)
        if not line.strip():
            continue
        _handle_command(line)


def OnMidiMsg(event):
    """Called on MIDI input. Not used by Studio AI."""
    pass


# ──────────────────── Command handling ────────────────────

def _handle_command(raw_line):
    """Parse and dispatch a single command."""
    try:
        cmd = json.loads(raw_line)
    except (ValueError, TypeError) as e:
        _log("Invalid JSON command: %s" % e)
        return

    cmd_id = cmd.get("id", "unknown")
    action = cmd.get("action", "")
    params = cmd.get("params", {})

    handler = _HANDLERS.get(action)
    if handler is None:
        _send_error(cmd_id, "Unknown action: %s" % action)
        return

    try:
        result = handler(params)
        _send_response(cmd_id, True, result)
    except Exception as e:
        _log("Action '%s' failed: %s" % (action, e))
        _send_error(cmd_id, str(e))


def _send_response(cmd_id, success, data=None):
    """Write a JSON response back to the plugin."""
    response = json.dumps({
        "id": cmd_id,
        "success": success,
        "data": data,
    })
    try:
        transport.write_response((response + "\n").encode("utf-8"))
    except Exception as e:
        _log("Failed to write response: %s" % e)


def _send_error(cmd_id, message):
    """Write an error response."""
    _send_response(cmd_id, False, {"error": message})


# ──────────────────── FL Studio action handlers ────────────────────

def _cmd_set_bpm(params):
    """Set project BPM. FL API expects value * 1000."""
    import general
    import midi
    bpm = params.get("bpm")
    if bpm is None or not (10 <= bpm <= 999):
        raise ValueError("BPM must be between 10 and 999, got: %s" % bpm)
    # FL Studio's internal tempo representation is BPM * 1000
    general.processRECEvent(
        midi.REC_Tempo,
        round(float(bpm) * 1000),
        midi.REC_Control | midi.REC_UpdateControl,
    )
    return {"bpm": bpm}


def _cmd_get_state(params):
    """Get current project state."""
    import general
    import mixer
    import transport

    bpm = float(mixer.getCurrentTempo()) / 1000.0
    project_name = general.getProjectTitle() or "Untitled"
    is_playing = transport.isPlaying()

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
    """Add a new channel to the Channel Rack."""
    import channels
    name = params.get("name", "New Track")
    idx = channels.channelCount()
    channels.setChannelName(idx, name)
    return {"index": idx, "name": name}


def _cmd_play(params):
    """Start playback."""
    import transport
    transport.start()
    return {"playing": True}


def _cmd_stop(params):
    """Stop playback."""
    import transport
    transport.stop()
    return {"playing": False}


def _cmd_record(params):
    """Toggle recording."""
    import transport
    transport.record()
    return {"recording": True}


def _cmd_set_track_volume(params):
    """Set mixer track volume (0.0 to 1.0)."""
    import mixer
    index = int(params.get("index", 0))
    volume = float(params.get("volume", 0.8))
    mixer.setTrackVolume(index, volume)
    return {"index": index, "volume": volume}


def _cmd_set_track_pan(params):
    """Set mixer track pan (-1.0 to 1.0)."""
    import mixer
    index = int(params.get("index", 0))
    pan = float(params.get("pan", 0.0))
    mixer.setTrackPan(index, pan)
    return {"index": index, "pan": pan}


def _cmd_set_track_mute(params):
    """Toggle mixer track mute."""
    import mixer
    index = int(params.get("index", 0))
    mixer.muteTrack(index)
    return {"index": index, "muted": bool(mixer.isTrackMuted(index))}


def _cmd_set_track_solo(params):
    """Toggle mixer track solo."""
    import mixer
    index = int(params.get("index", 0))
    mixer.soloTrack(index)
    return {"index": index, "solo": bool(mixer.isTrackSolo(index))}


def _cmd_rename_track(params):
    """Rename a mixer track."""
    import mixer
    index = int(params.get("index", 0))
    name = params.get("name", "")
    mixer.setTrackName(index, name)
    return {"index": index, "name": name}


# ──────────────────── Handler registry ────────────────────

_HANDLERS = {
    "set_bpm": _cmd_set_bpm,
    "get_state": _cmd_get_state,
    "get_project_state": _cmd_get_state,  # overridden below by ORGANIZE_HANDLERS
    "add_track": _cmd_add_track,
    "play": _cmd_play,
    "stop": _cmd_stop,
    "record": _cmd_record,
    "set_track_volume": _cmd_set_track_volume,
    "set_track_pan": _cmd_set_track_pan,
    "set_track_mute": _cmd_set_track_mute,
    "set_track_solo": _cmd_set_track_solo,
    "rename_track": _cmd_rename_track,
    **ORGANIZE_HANDLERS,  # organization agent handlers (overrides get_project_state)
}


# ──────────────────── Utility ────────────────────

def _log(msg):
    """Print to FL Studio's Script Output console."""
    print("[Studio AI] %s" % msg)
