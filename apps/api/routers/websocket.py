"""WebSocket endpoint for plugin connections."""

import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import httpx

from config import get_settings
from middleware.jwt_validation import validate_jwt, JWTValidationError
from services.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)
router = APIRouter()

# WebSocket close codes
WS_CLOSE_AUTH_FAILED = 4001
WS_CLOSE_SUBSCRIPTION_EXPIRED = 4003


async def check_subscription(user_id: str) -> bool:
    """Check if user has an active subscription via Supabase REST API."""
    settings = get_settings()
    url = f"{settings.supabase_url}/rest/v1/subscriptions"
    params = {"user_id": f"eq.{user_id}", "select": "status"}
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, headers=headers)
        if response.status_code != 200:
            logger.error("Supabase query failed: %s", response.text)
            return False

        data = response.json()
        if not data:
            # No subscription record — allow (free tier)
            return True

        status = data[0].get("status", "")
        return status in ("active",)


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Plugin WebSocket connection endpoint.

    Protocol:
    1. Accept connection
    2. First message must be: { "type": "auth", "payload": { "token": "jwt" } }
    3. Validate JWT -> extract user_id
    4. Check subscription status via Supabase
    5. Close 4001 if auth fails, 4003 if subscription expired
    6. Register in ConnectionManager
    7. Receive loop: heartbeat -> renew, response -> resolve, error -> resolve
    """
    await ws.accept()

    manager: ConnectionManager = ws.app.state.manager

    # Step 1: Wait for auth message
    try:
        raw = await ws.receive_text()
        message = json.loads(raw)
    except (WebSocketDisconnect, json.JSONDecodeError):
        await ws.close(code=WS_CLOSE_AUTH_FAILED, reason="Invalid auth message")
        return

    if message.get("type") != "auth" or "payload" not in message:
        await ws.close(code=WS_CLOSE_AUTH_FAILED, reason="Expected auth message")
        return

    token = message["payload"].get("token", "")

    # Step 2: Validate JWT
    try:
        payload = validate_jwt(token)
        user_id = payload["sub"]
    except JWTValidationError as e:
        logger.warning("Auth failed: %s", e.message)
        await ws.close(code=WS_CLOSE_AUTH_FAILED, reason=e.message)
        return

    # Step 3: Check subscription
    has_subscription = await check_subscription(user_id)
    if not has_subscription:
        await ws.close(
            code=WS_CLOSE_SUBSCRIPTION_EXPIRED,
            reason="Subscription expired or inactive",
        )
        return

    # Step 4: Register connection (already accepted above)
    manager.local[user_id] = ws
    await manager.redis.set(f"plugin:online:{user_id}", "1", ex=90)
    logger.info("User %s authenticated and registered", user_id)

    # Step 5: Receive loop
    try:
        while True:
            raw = await ws.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from user %s", user_id)
                continue

            msg_type = message.get("type")
            msg_id = message.get("id")

            if msg_type == "heartbeat":
                await manager.heartbeat(user_id)

            elif msg_type == "response" and msg_id:
                manager.resolve_response(msg_id, message)

            elif msg_type == "error" and msg_id:
                manager.resolve_response(msg_id, message)

            elif msg_type == "state":
                logger.debug("State update from user %s", user_id)

            else:
                logger.warning(
                    "Unknown message type '%s' from user %s", msg_type, user_id
                )

    except WebSocketDisconnect:
        logger.info("User %s disconnected", user_id)
    except Exception as e:
        logger.error("WebSocket error for user %s: %s", user_id, e)
    finally:
        await manager.disconnect(user_id)
