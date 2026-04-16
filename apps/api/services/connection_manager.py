"""WebSocket connection manager with Redis-backed state."""

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket
import redis.asyncio as aioredis

from services.redis_client import online_key, relay_channel, ONLINE_TTL_SECONDS

logger = logging.getLogger(__name__)

# How long to wait for the plugin to respond to a relayed action.
#
# The previous 5s value was too tight for `get_project_state` on the very
# first request after a WebSocket reconnect: the bridge still has to lazily
# establish its IPC pipe to FL, and FL has to enumerate channels/mixer/
# playlist/patterns in-process. On slower machines that easily overran 5s
# even after we trimmed the response payload (handlers_organize.py filters
# default-named slots). 30s is generous enough to cover that worst case
# without leaving a truly broken plugin hanging the user indefinitely.
RELAY_REQUEST_TIMEOUT_SECONDS = 30.0


class ConnectionManager:
    """Manages WebSocket connections with Redis-backed registry.

    - local: in-memory dict mapping user_id -> WebSocket
    - pending: dict mapping message_id -> asyncio.Future for relay correlation
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self.redis = redis
        self.local: dict[str, WebSocket] = {}
        self.pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

    async def connect(self, user_id: str, ws: WebSocket) -> None:
        """Accept and register a WebSocket connection."""
        await ws.accept()
        self.local[user_id] = ws
        await self.redis.set(online_key(user_id), "1", ex=ONLINE_TTL_SECONDS)
        logger.info("User %s connected", user_id)

    async def disconnect(self, user_id: str) -> None:
        """Remove a WebSocket connection from both local and Redis."""
        self.local.pop(user_id, None)
        await self.redis.delete(online_key(user_id))
        # Cancel any pending futures for this user
        pending_to_cancel = [
            (mid, fut)
            for mid, fut in self.pending.items()
            if not fut.done()
        ]
        for mid, fut in pending_to_cancel:
            fut.cancel()
        logger.info("User %s disconnected", user_id)

    async def heartbeat(self, user_id: str) -> None:
        """Renew the Redis TTL for a user's online status."""
        await self.redis.expire(online_key(user_id), ONLINE_TTL_SECONDS)

    async def is_online(self, user_id: str) -> bool:
        """Check if a user has an active connection (local or any instance)."""
        if user_id in self.local:
            return True
        return await self.redis.exists(online_key(user_id)) > 0

    async def relay_action(
        self, user_id: str, message: dict[str, Any]
    ) -> dict[str, Any]:
        """Send an action to the plugin and await the response.

        Creates an asyncio.Future keyed by the message ID, sends the message
        via the user's WebSocket, and waits up to RELAY_REQUEST_TIMEOUT_SECONDS
        for the response.

        Raises:
            TimeoutError: If no response within RELAY_REQUEST_TIMEOUT_SECONDS.
            ConnectionError: If the user is not connected locally.
        """
        ws = self.local.get(user_id)
        if ws is None:
            # Try cross-instance relay via Redis pub/sub
            is_online = await self.redis.exists(online_key(user_id))
            if is_online:
                await self.redis.publish(
                    relay_channel(user_id), json.dumps(message)
                )
                # For cross-instance, we still need a future
                loop = asyncio.get_running_loop()
                future: asyncio.Future[dict[str, Any]] = loop.create_future()
                self.pending[message["id"]] = future
                try:
                    return await asyncio.wait_for(
                        future, timeout=RELAY_REQUEST_TIMEOUT_SECONDS
                    )
                except asyncio.TimeoutError:
                    self.pending.pop(message["id"], None)
                    raise TimeoutError("RELAY_TIMEOUT")
            raise ConnectionError("PLUGIN_OFFLINE")

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self.pending[message["id"]] = future

        await ws.send_json(message)

        try:
            result = await asyncio.wait_for(
                future, timeout=RELAY_REQUEST_TIMEOUT_SECONDS
            )
            return result
        except asyncio.TimeoutError:
            self.pending.pop(message["id"], None)
            raise TimeoutError("RELAY_TIMEOUT")

    def resolve_response(self, message_id: str, response: dict[str, Any]) -> None:
        """Resolve a pending Future with the given response.

        Called when the WebSocket receive loop gets a response or error
        matching a pending relay request.
        """
        future = self.pending.pop(message_id, None)
        if future and not future.done():
            future.set_result(response)
        elif future is None:
            logger.warning("No pending future for message %s", message_id)
