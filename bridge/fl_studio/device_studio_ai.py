"""FL Studio MIDI Script entry point for Studio AI."""

import asyncio
import logging
import sys
import os

logging.basicConfig(level=logging.INFO, format="[StudioAI] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

bridge_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if bridge_dir not in sys.path:
    sys.path.insert(0, bridge_dir)

from bridge.core.server import BridgeServer
from bridge.core.actions import ActionRouter
from bridge.fl_studio.handlers import register_fl_handlers

_loop = None
_server = None


def OnInit():
    global _loop, _server
    logger.info("Studio AI bridge initializing...")
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    router = ActionRouter()
    register_fl_handlers(router)
    _server = BridgeServer(router)
    _loop.run_until_complete(_server.start())
    logger.info("Studio AI bridge ready on localhost:57120")


def OnDeInit():
    global _loop, _server
    logger.info("Studio AI bridge shutting down...")
    if _server and _loop:
        _loop.run_until_complete(_server.stop())
    if _loop:
        _loop.close()
    _loop = None
    _server = None


def OnIdle():
    global _loop
    if _loop is not None:
        _loop.run_until_complete(asyncio.sleep(0))


def OnMidiMsg(event):
    pass
