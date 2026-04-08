# name=Studio AI Respond
# url=https://studioai.app

"""FL Studio MIDI Script -- Studio AI Respond (Windows only).

Controller entry in FL Studio MIDI Settings:
  Input:  Studio AI Cmd
  Output: Studio AI Resp
  Port:   1   <- must match device_studio_ai_receive.py
  Type:   Studio AI Respond

Receives TAG_INTERNAL SysEx from device_studio_ai_receive.py via
FL Studio's internal port-1 bus and re-emits it as TAG_RESP on the
Studio AI Resp LoopMIDI port so the Rust plugin can receive it.

No business logic lives here -- this script is a pure relay.

Protocol:
  Inbound:  F0 7D 03 <base64(JSON)> F7  (TAG_INTERNAL from receive script)
  Outbound: F0 7D 02 <base64(JSON)> F7  (TAG_RESP to plugin via Studio AI Resp)
"""

import device

from _protocol import encode_sysex, decode_sysex, TAG_INTERNAL, TAG_RESP


# ---- FL Studio callbacks ----

def OnInit():
    _log("Studio AI Respond ready -- output: Studio AI Resp")


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


# ---- Utility ----

def _log(msg):
    print("[Studio AI Respond] " + str(msg))
