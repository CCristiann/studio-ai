"""Tests for message envelope parsing and serialization."""

import json
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from bridge.core.message import MessageEnvelope, make_response, make_error, make_state


def test_envelope_to_json():
    env = MessageEnvelope(id="test-1", type="action", payload={"action": "set_bpm", "params": {"bpm": 120}})
    data = json.loads(env.to_json())
    assert data["id"] == "test-1"
    assert data["type"] == "action"
    assert data["payload"]["action"] == "set_bpm"


def test_envelope_from_json():
    raw = json.dumps({"id": "test-2", "type": "response", "payload": {"success": True, "data": {"bpm": 140}}})
    env = MessageEnvelope.from_json(raw)
    assert env.id == "test-2"
    assert env.type == "response"
    assert env.payload["success"] is True


def test_envelope_from_json_missing_type():
    raw = json.dumps({"id": "test-3", "payload": {}})
    with pytest.raises(ValueError, match="missing 'type'"):
        MessageEnvelope.from_json(raw)


def test_envelope_from_json_invalid():
    with pytest.raises(ValueError, match="Invalid JSON"):
        MessageEnvelope.from_json("not json")


def test_envelope_from_json_not_object():
    with pytest.raises(ValueError, match="JSON object"):
        MessageEnvelope.from_json('"just a string"')


def test_envelope_auto_id():
    env = MessageEnvelope(type="heartbeat", payload={"timestamp": 12345})
    assert env.id
    assert len(env.id) == 36


def test_make_response():
    resp = make_response("req-1", True, {"bpm": 120})
    assert resp.id == "req-1"
    assert resp.type == "response"
    assert resp.payload["success"] is True
    assert resp.payload["data"]["bpm"] == 120


def test_make_response_failure():
    resp = make_response("req-2", False, None)
    assert resp.payload["success"] is False


def test_make_error():
    err = make_error("req-3", "DAW_TIMEOUT", "Action timed out")
    assert err.type == "error"
    assert err.payload["code"] == "DAW_TIMEOUT"


def test_make_state():
    state = make_state({"bpm": 128, "tracks": [], "project_name": "Test"})
    assert state.type == "state"
    assert state.payload["bpm"] == 128


def test_roundtrip():
    original = MessageEnvelope(id="rt-1", type="action", payload={"action": "play", "params": {}})
    json_str = original.to_json()
    parsed = MessageEnvelope.from_json(json_str)
    assert parsed.id == original.id
    assert parsed.type == original.type
    assert parsed.payload == original.payload
