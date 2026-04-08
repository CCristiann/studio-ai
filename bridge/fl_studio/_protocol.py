"""SysEx protocol helpers for Studio AI.

Shared by device_studio_ai_receive.py and device_studio_ai_respond.py.
No FL Studio API imports — this module can be imported and tested
outside FL Studio.

Wire format:
    F0  7D  [TAG]  [base64(UTF-8 JSON)]  F7

Tags:
    TAG_CMD      = 0x01  — plugin -> receive script (external, via Studio AI Cmd)
    TAG_RESP     = 0x02  — respond script -> plugin (external, via Studio AI Resp)
    TAG_INTERNAL = 0x03  — receive script -> respond script (FL internal port bus)
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
        bytes -- complete SysEx message including F0 / F7 framing.
    """
    encoded = base64.b64encode(json_str.encode("utf-8"))  # pure ASCII bytes
    return bytes([_SYSEX_START, MFR_ID, tag]) + encoded + bytes([_SYSEX_END])


def decode_sysex(data):
    """Parse a SysEx message and return (tag, json_str).

    Args:
        data: bytes -- the raw SysEx bytes including F0 / F7 framing.

    Returns:
        (tag: int, json_str: str)

    Raises:
        ValueError -- if the message is malformed or not from Studio AI.
    """
    if not data or len(data) < 5:
        raise ValueError("SysEx too short: " + str(len(data) if data else 0))
    if data[0] != _SYSEX_START or data[-1] != _SYSEX_END:
        raise ValueError("Missing F0/F7 framing")
    if data[1] != MFR_ID:
        raise ValueError("Wrong manufacturer ID: " + hex(data[1]))
    tag = data[2]
    payload_bytes = data[3:-1]
    try:
        json_str = base64.b64decode(payload_bytes).decode("utf-8")
    except Exception:
        # Fallback: old plugin versions send raw UTF-8 JSON (no base64)
        try:
            json_str = payload_bytes.decode("utf-8")
        except Exception as e:
            raise ValueError("Payload decode error: " + str(e))
    return tag, json_str
