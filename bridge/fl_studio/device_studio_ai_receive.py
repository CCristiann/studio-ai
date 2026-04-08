# name=Studio AI Receive
# url=https://studioai.app

"""FL Studio MIDI Script -- Studio AI Receive (Windows only).

Controller entry in FL Studio MIDI Settings:
  Input:  Studio AI Cmd
  Output: (none -- do not set)
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


# ---- FL Studio callbacks ----

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

    _log("sysex bytes[0:8]: " + " ".join(hex(b) for b in raw[:8]))

    try:
        tag, json_str = decode_sysex(raw)
    except ValueError as e:
        _log("decode error: " + str(e))
        return

    if tag != TAG_CMD:
        return  # ignore TAG_RESP and TAG_INTERNAL echoes on this port

    _handle_command(json_str)


# ---- Command dispatch ----

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
    import os
    payload = json.dumps({"id": cmd_id, "success": success, "data": data})
    # Write response to file — plugin polls this file since MIDI internal
    # bus routing between FL scripts is unreliable on Windows.
    resp_dir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Studio AI", "resp")
    try:
        os.makedirs(resp_dir, exist_ok=True)
        resp_file = os.path.join(resp_dir, cmd_id + ".json")
        with open(resp_file, "w", encoding="utf-8") as f:
            f.write(payload)
    except Exception as e:
        _log("write response file failed: " + str(e))


# ---- Handlers ----

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
    # channelCount() returns the count; index = count is out of range until a
    # new channel is added. FL Studio has no public addChannel() API in the
    # scripting SDK, so we return a descriptive error instead of silently failing.
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


# ---- Handler registry ----

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


# ---- Utility ----

def _log(msg):
    print("[Studio AI Receive] " + str(msg))
