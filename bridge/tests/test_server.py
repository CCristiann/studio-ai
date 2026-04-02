"""Tests for the bridge WebSocket server."""

import asyncio
import json
import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import websockets
from bridge.core.server import BridgeServer
from bridge.core.actions import ActionRouter
from bridge.core.message import MessageEnvelope


@pytest.fixture
def router():
    r = ActionRouter()

    async def mock_set_bpm(params):
        return {"bpm": params["bpm"]}

    async def mock_get_state(params):
        return {"bpm": 120, "tracks": [], "project_name": "Test"}

    r.register("set_bpm", mock_set_bpm)
    r.register("get_state", mock_get_state)
    return r


@pytest.fixture
async def server(router):
    srv = BridgeServer(router, port=57121)
    await srv.start()
    yield srv
    await srv.stop()


@pytest.mark.asyncio
async def test_server_auth_success(server):
    async with websockets.connect("ws://localhost:57121") as ws:
        auth_msg = json.dumps({"type": "auth", "payload": {"token": server.token}})
        await ws.send(auth_msg)

        action = MessageEnvelope(id="test-1", type="action", payload={"action": "set_bpm", "params": {"bpm": 140}})
        await ws.send(action.to_json())

        raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
        response = json.loads(raw)
        assert response["id"] == "test-1"
        assert response["type"] == "response"
        assert response["payload"]["success"] is True
        assert response["payload"]["data"]["bpm"] == 140


@pytest.mark.asyncio
async def test_server_auth_failure(server):
    async with websockets.connect("ws://localhost:57121") as ws:
        auth_msg = json.dumps({"type": "auth", "payload": {"token": "wrong-token"}})
        await ws.send(auth_msg)
        try:
            await asyncio.wait_for(ws.recv(), timeout=2.0)
            assert False, "Should have been disconnected"
        except (websockets.ConnectionClosed, asyncio.TimeoutError):
            pass


@pytest.mark.asyncio
async def test_server_unknown_action(server):
    async with websockets.connect("ws://localhost:57121") as ws:
        auth_msg = json.dumps({"type": "auth", "payload": {"token": server.token}})
        await ws.send(auth_msg)

        action = MessageEnvelope(id="test-2", type="action", payload={"action": "nonexistent", "params": {}})
        await ws.send(action.to_json())

        raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
        response = json.loads(raw)
        assert response["type"] == "error"
        assert response["payload"]["code"] == "DAW_ERROR"


@pytest.mark.asyncio
async def test_server_get_state(server):
    async with websockets.connect("ws://localhost:57121") as ws:
        auth_msg = json.dumps({"type": "auth", "payload": {"token": server.token}})
        await ws.send(auth_msg)

        action = MessageEnvelope(id="test-3", type="action", payload={"action": "get_state", "params": {}})
        await ws.send(action.to_json())

        raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
        response = json.loads(raw)
        assert response["type"] == "response"
        assert response["payload"]["data"]["bpm"] == 120
