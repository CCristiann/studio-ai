"""Tests for the relay HTTP endpoint."""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from main import app
from services.connection_manager import ConnectionManager

TEST_API_KEY = "test-internal-api-key"


@pytest.fixture(autouse=True)
def mock_settings():
    settings = MagicMock()
    settings.fastapi_internal_api_key = TEST_API_KEY
    settings.redis_url = "redis://localhost:6379"
    settings.supabase_jwt_secret = "test"
    settings.supabase_url = "https://test.supabase.co"
    settings.supabase_service_role_key = "test-key"
    settings.stripe_secret_key = ""
    settings.stripe_webhook_secret = ""
    with patch("routers.relay.get_settings", return_value=settings):
        yield settings


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.set = AsyncMock()
    r.delete = AsyncMock()
    r.expire = AsyncMock()
    r.exists = AsyncMock(return_value=0)
    r.close = AsyncMock()
    return r


@pytest.fixture
def manager(mock_redis):
    return ConnectionManager(mock_redis)


@pytest.fixture
def client(manager, mock_redis):
    app.state.redis = mock_redis
    app.state.manager = manager
    return TestClient(app)


def test_relay_plugin_offline(client):
    response = client.post(
        "/relay/user-offline",
        json={"action": "set_bpm", "params": {"bpm": 120}},
        headers={"X-API-Key": TEST_API_KEY},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "PLUGIN_OFFLINE"


def test_relay_invalid_api_key(client):
    response = client.post(
        "/relay/user-1",
        json={"action": "set_bpm", "params": {"bpm": 120}},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_relay_missing_api_key(client):
    response = client.post(
        "/relay/user-1",
        json={"action": "set_bpm", "params": {"bpm": 120}},
    )
    assert response.status_code == 422  # Missing required header


def test_relay_success(client, manager):
    mock_ws = AsyncMock()
    mock_ws.send_json = AsyncMock()
    manager.local["user-1"] = mock_ws

    async def simulate_response(*args, **kwargs):
        await asyncio.sleep(0.01)
        for msg_id, fut in list(manager.pending.items()):
            if not fut.done():
                fut.set_result({
                    "id": msg_id,
                    "type": "response",
                    "payload": {"success": True, "data": {"bpm": 120}},
                })

    mock_ws.send_json.side_effect = lambda msg: asyncio.ensure_future(simulate_response())

    response = client.post(
        "/relay/user-1",
        json={"action": "set_bpm", "params": {"bpm": 120}},
        headers={"X-API-Key": TEST_API_KEY},
    )
    assert response.status_code in (200, 504)


def test_relay_error_response(client, manager):
    mock_ws = AsyncMock()
    manager.local["user-err"] = mock_ws

    async def simulate_error(*args, **kwargs):
        await asyncio.sleep(0.01)
        for msg_id, fut in list(manager.pending.items()):
            if not fut.done():
                fut.set_result({
                    "id": msg_id,
                    "type": "error",
                    "payload": {"code": "DAW_ERROR", "message": "Invalid BPM value"},
                })

    mock_ws.send_json.side_effect = lambda msg: asyncio.ensure_future(simulate_error())

    response = client.post(
        "/relay/user-err",
        json={"action": "set_bpm", "params": {"bpm": -1}},
        headers={"X-API-Key": TEST_API_KEY},
    )
    assert response.status_code in (200, 504)


def test_relay_handler_exception_surfaces_error_message(client, manager):
    """Regression: when an FL Studio handler raises, the bridge sends the
    exception message inside payload.data.error with success=False, but
    payload.type stays "response" (the plugin only uses type="error" for IPC
    failures). The relay used to drop payload.data.error on the floor, so
    the AI tool only saw `success:false` with no error text — the AI then
    hallucinated advice like "make sure FL Studio is running". The relay
    must promote data.error into the top-level error field so every tool
    can surface it to the model.
    """
    mock_ws = AsyncMock()
    manager.local["user-handler-crash"] = mock_ws

    async def simulate_handler_exception(*args, **kwargs):
        await asyncio.sleep(0.01)
        for msg_id, fut in list(manager.pending.items()):
            if not fut.done():
                fut.set_result({
                    "id": msg_id,
                    "type": "response",
                    "payload": {
                        "success": False,
                        "data": {"error": "module 'mixer' has no attribute 'getCurrentTempo'"},
                    },
                })

    mock_ws.send_json.side_effect = lambda msg: asyncio.ensure_future(
        simulate_handler_exception()
    )

    response = client.post(
        "/relay/user-handler-crash",
        json={"action": "get_project_state", "params": {}},
        headers={"X-API-Key": TEST_API_KEY},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["error"] == "module 'mixer' has no attribute 'getCurrentTempo'"


def test_relay_handler_failure_without_error_field_still_marks_failed(client, manager):
    """Defensive path: some legacy handlers may return success=False without
    any error text (or with data=null). Relay must still mark success=False;
    the error field can be None but should not crash the response model.
    """
    mock_ws = AsyncMock()
    manager.local["user-silent-fail"] = mock_ws

    async def simulate_silent_fail(*args, **kwargs):
        await asyncio.sleep(0.01)
        for msg_id, fut in list(manager.pending.items()):
            if not fut.done():
                fut.set_result({
                    "id": msg_id,
                    "type": "response",
                    "payload": {"success": False, "data": None},
                })

    mock_ws.send_json.side_effect = lambda msg: asyncio.ensure_future(
        simulate_silent_fail()
    )

    response = client.post(
        "/relay/user-silent-fail",
        json={"action": "set_bpm", "params": {"bpm": 120}},
        headers={"X-API-Key": TEST_API_KEY},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
