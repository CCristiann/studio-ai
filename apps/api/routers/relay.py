"""HTTP relay endpoint for Next.js to send actions to plugins."""

import uuid
import logging
from typing import Any

from fastapi import APIRouter, Request, HTTPException, Header
from pydantic import BaseModel

from config import get_settings
from services.connection_manager import ConnectionManager, RELAY_REQUEST_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)
router = APIRouter()


class RelayRequest(BaseModel):
    """Action payload from Next.js AI tool execution."""

    action: str
    params: dict[str, Any] = {}


class RelayResponse(BaseModel):
    """Response returned to Next.js."""

    id: str
    success: bool
    data: Any = None
    error: str | None = None
    code: str | None = None


def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Verify the internal API key shared between Next.js and FastAPI."""
    settings = get_settings()
    if x_api_key != settings.fastapi_internal_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


@router.post("/relay/{user_id}", response_model=RelayResponse)
async def relay_action(
    user_id: str,
    body: RelayRequest,
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
):
    """Relay an action from Next.js to a user's connected plugin."""
    settings = get_settings()
    if x_api_key != settings.fastapi_internal_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    manager: ConnectionManager = request.app.state.manager

    is_online = await manager.is_online(user_id)
    if not is_online:
        raise HTTPException(
            status_code=503,
            detail={"code": "PLUGIN_OFFLINE", "message": "No active plugin connection for this user"},
        )

    message_id = str(uuid.uuid4())
    message = {
        "id": message_id,
        "type": "action",
        "payload": {
            "action": body.action,
            "params": body.params,
        },
    }

    try:
        result = await manager.relay_action(user_id, message)
    except TimeoutError:
        raise HTTPException(
            status_code=504,
            detail={
                "code": "RELAY_TIMEOUT",
                "message": (
                    "Plugin did not respond within "
                    f"{int(RELAY_REQUEST_TIMEOUT_SECONDS)} seconds"
                ),
            },
        )
    except ConnectionError as e:
        error_code = str(e)
        if error_code == "PLUGIN_OFFLINE":
            raise HTTPException(
                status_code=503,
                detail={"code": "PLUGIN_OFFLINE", "message": "Plugin went offline during relay"},
            )
        raise HTTPException(
            status_code=502,
            detail={"code": "BRIDGE_DISCONNECTED", "message": "Bridge is not reachable"},
        )

    result_type = result.get("type")
    result_payload = result.get("payload", {})

    if result_type == "error":
        error_code = result_payload.get("code", "DAW_ERROR")
        error_message = result_payload.get("message", "Unknown error")
        return RelayResponse(
            id=message_id,
            success=False,
            error=error_message,
            code=error_code,
        )

    return RelayResponse(
        id=message_id,
        success=result_payload.get("success", True),
        data=result_payload.get("data"),
    )
