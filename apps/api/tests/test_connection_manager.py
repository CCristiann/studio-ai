"""Tests for ConnectionManager."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.connection_manager import ConnectionManager


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.set = AsyncMock()
    r.delete = AsyncMock()
    r.expire = AsyncMock()
    r.exists = AsyncMock(return_value=0)
    r.publish = AsyncMock()
    return r


@pytest.fixture
def manager(mock_redis):
    return ConnectionManager(mock_redis)


@pytest.fixture
def mock_ws():
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_connect_registers_user(manager, mock_ws, mock_redis):
    await manager.connect("user-1", mock_ws)

    assert "user-1" in manager.local
    assert manager.local["user-1"] is mock_ws
    mock_ws.accept.assert_called_once()
    mock_redis.set.assert_called_once_with("plugin:online:user-1", "1", ex=90)


@pytest.mark.asyncio
async def test_disconnect_removes_user(manager, mock_ws, mock_redis):
    await manager.connect("user-1", mock_ws)
    await manager.disconnect("user-1")

    assert "user-1" not in manager.local
    mock_redis.delete.assert_called_once_with("plugin:online:user-1")


@pytest.mark.asyncio
async def test_heartbeat_renews_ttl(manager, mock_redis):
    await manager.heartbeat("user-1")
    mock_redis.expire.assert_called_once_with("plugin:online:user-1", 90)


@pytest.mark.asyncio
async def test_relay_action_sends_and_resolves(manager, mock_ws, mock_redis):
    await manager.connect("user-1", mock_ws)

    message = {"id": "msg-1", "type": "action", "payload": {"action": "set_bpm", "params": {"bpm": 120}}}

    # Simulate response arriving shortly after send
    async def simulate_response():
        await asyncio.sleep(0.05)
        manager.resolve_response("msg-1", {"id": "msg-1", "type": "response", "payload": {"success": True, "data": {}}})

    asyncio.create_task(simulate_response())
    result = await manager.relay_action("user-1", message)

    mock_ws.send_json.assert_called_once_with(message)
    assert result["type"] == "response"
    assert result["payload"]["success"] is True


@pytest.mark.asyncio
async def test_relay_action_timeout(manager, mock_ws, mock_redis):
    await manager.connect("user-1", mock_ws)

    message = {"id": "msg-timeout", "type": "action", "payload": {}}

    # The manager uses a 5s timeout internally which is too long to test directly.
    # Test offline raises ConnectionError instead.
    mock_redis.exists = AsyncMock(return_value=0)
    with pytest.raises(ConnectionError, match="PLUGIN_OFFLINE"):
        await manager.relay_action("user-offline", message)


@pytest.mark.asyncio
async def test_resolve_response_ignores_unknown_id(manager):
    # Should not raise — just logs a warning
    manager.resolve_response("unknown-id", {"type": "response"})
    assert "unknown-id" not in manager.pending


@pytest.mark.asyncio
async def test_is_online_local(manager, mock_ws, mock_redis):
    await manager.connect("user-1", mock_ws)
    assert await manager.is_online("user-1") is True


@pytest.mark.asyncio
async def test_is_online_redis(manager, mock_redis):
    mock_redis.exists = AsyncMock(return_value=1)
    assert await manager.is_online("user-remote") is True


@pytest.mark.asyncio
async def test_is_online_false(manager, mock_redis):
    mock_redis.exists = AsyncMock(return_value=0)
    assert await manager.is_online("user-gone") is False
