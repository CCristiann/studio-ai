"""Action router — dispatches incoming actions to DAW-specific handlers."""

import asyncio
import logging
from typing import Any, Callable, Awaitable

from bridge.core.message import MessageEnvelope, make_response, make_error

logger = logging.getLogger(__name__)

ActionHandler = Callable[[dict[str, Any]], Awaitable[Any]]
DAW_ACTION_TIMEOUT = 4.0


class ActionRouter:
    def __init__(self) -> None:
        self.handlers: dict[str, ActionHandler] = {}

    def register(self, action_name: str, handler: ActionHandler) -> None:
        self.handlers[action_name] = handler
        logger.info("Registered handler for action: %s", action_name)

    async def execute(self, envelope: MessageEnvelope) -> MessageEnvelope:
        action = envelope.payload.get("action", "")
        params = envelope.payload.get("params", {})

        handler = self.handlers.get(action)
        if handler is None:
            return make_error(envelope.id, "DAW_ERROR", f"Unknown action: {action}")

        try:
            result = await asyncio.wait_for(handler(params), timeout=DAW_ACTION_TIMEOUT)
            return make_response(envelope.id, True, result)
        except asyncio.TimeoutError:
            return make_error(envelope.id, "DAW_TIMEOUT", f"Action '{action}' timed out after {DAW_ACTION_TIMEOUT}s")
        except Exception as e:
            logger.exception("Action '%s' failed", action)
            return make_error(envelope.id, "DAW_ERROR", str(e))
