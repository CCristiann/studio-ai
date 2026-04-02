"""WebSocket server for the DAW bridge."""

import asyncio
import json
import logging
from typing import Optional

import websockets
from websockets.server import ServerConnection

from bridge.core.auth import ensure_token, validate_token
from bridge.core.message import MessageEnvelope
from bridge.core.actions import ActionRouter

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 57120


class BridgeServer:
    def __init__(self, router: ActionRouter, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        self.router = router
        self.host = host
        self.port = port
        self.token = ensure_token()
        self.connected_client: Optional[ServerConnection] = None
        self._server = None

    async def start(self) -> None:
        self._server = await websockets.serve(self._handle_connection, self.host, self.port)
        logger.info("Bridge server listening on %s:%d", self.host, self.port)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("Bridge server stopped")

    async def _handle_connection(self, websocket: ServerConnection) -> None:
        logger.info("Plugin connecting from %s", websocket.remote_address)

        try:
            raw = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            message = json.loads(raw)
        except (asyncio.TimeoutError, json.JSONDecodeError) as e:
            logger.warning("Auth failed: %s", e)
            await websocket.close(4001, "Invalid auth message")
            return

        if message.get("type") != "auth":
            await websocket.close(4001, "Expected auth message")
            return

        provided_token = message.get("payload", {}).get("token", "")
        if not validate_token(provided_token, self.token):
            logger.warning("Bridge token validation failed")
            await websocket.close(4001, "Invalid bridge token")
            return

        logger.info("Plugin authenticated successfully")
        self.connected_client = websocket

        try:
            async for raw in websocket:
                try:
                    envelope = MessageEnvelope.from_json(raw)
                except ValueError as e:
                    logger.warning("Invalid message: %s", e)
                    continue

                if envelope.type == "action":
                    response = await self.router.execute(envelope)
                    await websocket.send(response.to_json())
                elif envelope.type == "heartbeat":
                    logger.debug("Heartbeat from plugin")
                else:
                    logger.debug("Unhandled message type: %s", envelope.type)

        except websockets.ConnectionClosed:
            logger.info("Plugin disconnected")
        finally:
            self.connected_client = None
