"""Message envelope parsing and serialization."""

import json
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class MessageEnvelope:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "MessageEnvelope":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
        if not isinstance(data, dict):
            raise ValueError("Message must be a JSON object")
        if "type" not in data:
            raise ValueError("Message missing 'type' field")
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            type=data["type"],
            payload=data.get("payload", {}),
        )


def make_response(request_id: str, success: bool, data: Any = None) -> MessageEnvelope:
    return MessageEnvelope(id=request_id, type="response", payload={"success": success, "data": data})


def make_error(request_id: str, code: str, message: str) -> MessageEnvelope:
    return MessageEnvelope(id=request_id, type="error", payload={"code": code, "message": message})


def make_state(state_data: dict[str, Any]) -> MessageEnvelope:
    return MessageEnvelope(type="state", payload=state_data)
