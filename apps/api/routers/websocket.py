"""WebSocket endpoint for plugin connections."""

import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import httpx

from config import get_settings
from middleware.jwt_validation import validate_jwt, JWTValidationError
from services.connection_manager import ConnectionManager
from services.jti_revocation import is_jti_revoked, RevocationLookupError

logger = logging.getLogger(__name__)
router = APIRouter()

# WebSocket close codes
WS_CLOSE_AUTH_FAILED = 4001
WS_CLOSE_SUBSCRIPTION_EXPIRED = 4003

# Bound the first-message-auth fallback to limit unauthenticated socket
# lifetime (DoS surface). The handshake-auth path skips this entirely.
LEGACY_AUTH_TIMEOUT_SECONDS = 5.0

# How often to recheck jti revocation while the socket is open (audit H3).
# Kept at 5 min to balance detection latency against DB pressure — combined
# with the 4-min Redis cache, the expected Supabase RPS per user is <0.5/hr.
JTI_RECHECK_INTERVAL_SECONDS = 300.0


async def _jti_recheck_loop(
    ws: WebSocket,
    jti: str,
    redis,
    settings,
    interval: float = JTI_RECHECK_INTERVAL_SECONDS,
) -> None:
    """Background task: periodically recheck jti revocation; close on revoke.

    On RevocationLookupError we log and continue — a transient Supabase
    outage shouldn't boot active producers mid-session. Worst case: a
    revocation takes one extra cycle to propagate once Supabase recovers.
    """
    while True:
        await asyncio.sleep(interval)
        try:
            revoked = await is_jti_revoked(jti, redis, settings)
        except RevocationLookupError as e:
            logger.warning(
                "jti recheck lookup failed for %s: %s — keeping socket alive",
                jti,
                e,
            )
            continue
        if revoked:
            logger.info("jti %s revoked — closing WSS", jti)
            await ws.close(code=WS_CLOSE_AUTH_FAILED, reason="Token revoked")
            return


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


async def _check_jti_or_close(
    ws: WebSocket, jti: str, redis, settings
) -> bool:
    """Handshake-time revocation check. Returns True if OK to proceed.

    On revoked or lookup error, closes the socket and returns False.
    Pre-accept close gives the client HTTP 403; post-accept close uses
    WS_CLOSE_AUTH_FAILED. The caller decides which state it's in.
    """
    try:
        revoked = await is_jti_revoked(jti, redis, settings)
    except RevocationLookupError as e:
        logger.warning("Handshake jti lookup failed for %s: %s", jti, e)
        await ws.close(code=WS_CLOSE_AUTH_FAILED, reason="Revocation check failed")
        return False
    if revoked:
        logger.info("Handshake rejected revoked jti %s", jti)
        await ws.close(code=WS_CLOSE_AUTH_FAILED, reason="Token revoked")
        return False
    return True


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

    After auth: jti revocation check (plugin tokens only) → subscription check
    → register in ConnectionManager → start recheck loop → receive loop.
    """
    handshake_token = _extract_bearer_token(ws)
    manager: ConnectionManager = ws.app.state.manager
    settings = get_settings()

    user_id: str | None = None
    jti: str | None = None

    if handshake_token is not None:
        # Handshake-auth path: validate before accept so bad tokens never
        # consume an accepted-socket slot.
        try:
            payload = validate_jwt(handshake_token)
            user_id = payload["sub"]
            jti = payload.get("jti")
        except JWTValidationError as e:
            logger.warning("Handshake auth failed: %s", e.message)
            await ws.close(code=WS_CLOSE_AUTH_FAILED, reason=e.message)
            return

        # jti revocation check (audit H3). Only plugin tokens carry a jti.
        # Pre-accept close → HTTP 403.
        if jti is not None:
            if not await _check_jti_or_close(ws, jti, manager.redis, settings):
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
            jti = payload.get("jti")
        except JWTValidationError as e:
            logger.warning("First-message auth failed: %s", e.message)
            await ws.close(code=WS_CLOSE_AUTH_FAILED, reason=e.message)
            return

        # Post-accept revocation check.
        if jti is not None:
            if not await _check_jti_or_close(ws, jti, manager.redis, settings):
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

    # Step 5: Periodic jti recheck task (plugin tokens only).
    recheck_task: asyncio.Task | None = None
    if jti is not None:
        recheck_task = asyncio.create_task(
            _jti_recheck_loop(ws, jti, manager.redis, settings)
        )

    # Step 6: Receive loop
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
        if recheck_task is not None and not recheck_task.done():
            recheck_task.cancel()
        await manager.disconnect(user_id)
