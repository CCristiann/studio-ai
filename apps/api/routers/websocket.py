"""WebSocket endpoint for plugin connections."""

import asyncio
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

# Bound the first-message-auth fallback to limit unauthenticated socket
# lifetime (DoS surface). The handshake-auth path skips this entirely.
LEGACY_AUTH_TIMEOUT_SECONDS = 5.0


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
            # No subscription row — deny. New users get a free/active row
            # provisioned by the next_auth.users INSERT trigger
            # (migration 009). A missing row means provisioning failed
            # or the user was created before the trigger existed.
            logger.warning("No subscription row for user %s — denying", user_id)
            return False

        return data[0].get("status") == "active"


def _extract_bearer_token(ws: WebSocket) -> str | None:
    """Return the bearer token from the Authorization header, or None if absent."""
    header = ws.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Plugin WebSocket connection endpoint.

    Auth resolution order:
    1. Handshake auth — `Authorization: Bearer <jwt>` in the upgrade request.
       Validated **before** `accept()`. Invalid token → close pre-accept (HTTP 403).
       This is the path new plugin builds use.
    2. Legacy first-message auth — only attempted if no Authorization header is
       present. Tightened with a 5s timeout so unauthenticated sockets cannot
       hold resources indefinitely. Drop after the plugin handshake-auth
       release reaches all installed users.

    After auth: subscription check → register in ConnectionManager → receive loop.
    """
    handshake_token = _extract_bearer_token(ws)

    user_id: str | None = None

    if handshake_token is not None:
        # Handshake-auth path: validate before accept so bad tokens never
        # consume an accepted-socket slot.
        try:
            payload = validate_jwt(handshake_token)
            user_id = payload["sub"]
        except JWTValidationError as e:
            logger.warning("Handshake auth failed: %s", e.message)
            await ws.close(code=WS_CLOSE_AUTH_FAILED, reason=e.message)
            return
        await ws.accept()
    else:
        # Legacy first-message-auth path. Strict 5s timeout bounds
        # the unauthenticated socket lifetime.
        await ws.accept()
        try:
            raw = await asyncio.wait_for(
                ws.receive_text(), timeout=LEGACY_AUTH_TIMEOUT_SECONDS
            )
            message = json.loads(raw)
        except asyncio.TimeoutError:
            await ws.close(code=WS_CLOSE_AUTH_FAILED, reason="Auth timeout")
            return
        except (WebSocketDisconnect, json.JSONDecodeError):
            await ws.close(code=WS_CLOSE_AUTH_FAILED, reason="Invalid auth message")
            return

        if message.get("type") != "auth" or "payload" not in message:
            await ws.close(code=WS_CLOSE_AUTH_FAILED, reason="Expected auth message")
            return

        token = message["payload"].get("token", "")
        try:
            payload = validate_jwt(token)
            user_id = payload["sub"]
        except JWTValidationError as e:
            logger.warning("First-message auth failed: %s", e.message)
            await ws.close(code=WS_CLOSE_AUTH_FAILED, reason=e.message)
            return

    manager: ConnectionManager = ws.app.state.manager

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
