"""Tests for WebSocket endpoint."""

import json
import time
import jwt as pyjwt
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

from main import app

TEST_SECRET = "test-secret-key-ws"


def make_token(sub: str = "user-ws-1", exp_offset: int = 3600) -> str:
    payload = {
        "sub": sub,
        "email": "test@example.com",
        "role": "authenticated",
        "aud": "authenticated",
        "exp": int(time.time()) + exp_offset,
    }
    return pyjwt.encode(payload, TEST_SECRET, algorithm="HS256")


@pytest.fixture(autouse=True)
def mock_settings():
    settings = MagicMock()
    settings.supabase_jwt_secret = TEST_SECRET
    settings.supabase_url = "https://test.supabase.co"
    settings.supabase_service_role_key = "test-key"
    settings.redis_url = "redis://localhost:6379"
    settings.fastapi_internal_api_key = "test-api-key"
    settings.stripe_secret_key = ""
    settings.stripe_webhook_secret = ""
    with patch("middleware.jwt_validation.get_settings", return_value=settings):
        with patch("routers.websocket.get_settings", return_value=settings):
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
def client(mock_redis):
    from services.connection_manager import ConnectionManager

    app.state.redis = mock_redis
    app.state.manager = ConnectionManager(mock_redis)
    return TestClient(app)


def test_ws_auth_success(client):
    with patch("routers.websocket.check_subscription", return_value=True):
        with client.websocket_connect("/ws") as ws:
            token = make_token()
            ws.send_text(json.dumps({
                "type": "auth",
                "payload": {"token": token},
            }))
            # Send heartbeat to verify connection is alive
            ws.send_text(json.dumps({
                "type": "heartbeat",
                "id": "hb-1",
                "payload": {"timestamp": int(time.time())},
            }))


def test_ws_auth_invalid_token(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({
            "type": "auth",
            "payload": {"token": "garbage-token"},
        }))


def test_ws_auth_missing_type(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({
            "type": "not-auth",
            "payload": {},
        }))


def test_ws_subscription_expired(client):
    with patch("routers.websocket.check_subscription", return_value=False):
        with client.websocket_connect("/ws") as ws:
            token = make_token()
            ws.send_text(json.dumps({
                "type": "auth",
                "payload": {"token": token},
            }))


@pytest.mark.asyncio
async def test_check_subscription_no_row_denies():
    """Audit fix H1: missing subscription row must deny, not fall through to free tier."""
    from routers.websocket import check_subscription

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value=[])

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("routers.websocket.httpx.AsyncClient", return_value=mock_client):
        result = await check_subscription("user-with-no-row")

    assert result is False


@pytest.mark.asyncio
async def test_check_subscription_active_row_allows():
    from routers.websocket import check_subscription

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value=[{"status": "active"}])

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("routers.websocket.httpx.AsyncClient", return_value=mock_client):
        result = await check_subscription("user-active")

    assert result is True


@pytest.mark.asyncio
async def test_check_subscription_canceled_denies():
    from routers.websocket import check_subscription

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value=[{"status": "canceled"}])

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("routers.websocket.httpx.AsyncClient", return_value=mock_client):
        result = await check_subscription("user-canceled")

    assert result is False


def test_ws_response_resolves_future(client):
    with patch("routers.websocket.check_subscription", return_value=True):
        with client.websocket_connect("/ws") as ws:
            token = make_token()
            ws.send_text(json.dumps({
                "type": "auth",
                "payload": {"token": token},
            }))

            # Send a response message (simulating plugin response)
            ws.send_text(json.dumps({
                "id": "msg-1",
                "type": "response",
                "payload": {"success": True, "data": {"bpm": 120}},
            }))


# ── Handshake auth (ADR 2026-04-15-ws-handshake-auth) ──


def test_ws_handshake_auth_success(client):
    """Authorization header in the handshake authenticates the connection without a first-message."""
    token = make_token()
    with patch("routers.websocket.check_subscription", return_value=True):
        with client.websocket_connect(
            "/ws", headers={"Authorization": f"Bearer {token}"}
        ) as ws:
            ws.send_text(json.dumps({
                "type": "heartbeat",
                "id": "hb-1",
                "payload": {"timestamp": int(time.time())},
            }))


def test_ws_handshake_auth_bad_token_rejected(client):
    """Bad token in handshake must close before accept."""
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/ws", headers={"Authorization": "Bearer not-a-real-token"}
        ) as ws:
            ws.receive_text()


def test_ws_handshake_auth_skips_first_message(client):
    """When handshake auth wins, server should NOT wait for a first-message auth."""
    token = make_token()
    with patch("routers.websocket.check_subscription", return_value=True):
        with client.websocket_connect(
            "/ws", headers={"Authorization": f"Bearer {token}"}
        ) as ws:
            # Send a non-auth message immediately. If the server were still
            # gating on first-message auth, it would close us with code 4001.
            ws.send_text(json.dumps({
                "id": "msg-1",
                "type": "response",
                "payload": {"success": True},
            }))
