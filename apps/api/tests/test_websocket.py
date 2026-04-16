"""Tests for WebSocket endpoint."""

import json
import time
import jwt as pyjwt
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

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


@pytest.fixture(scope="module")
def rsa_keypair():
    """Generate a fresh RSA keypair once per module for plugin-token tests."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def make_plugin_token(
    user_id: str = "user-plugin-ws",
    jti: str = "jti-test",
    exp_offset: int = 3600,
    private_key: str = "",
) -> str:
    """Sign a Studio AI plugin JWT (RS256) for handshake auth tests."""
    payload = {
        "userId": user_id,
        "jti": jti,
        "iss": "studio-ai",
        "aud": "studio-ai-plugin",
        "exp": int(time.time()) + exp_offset,
        "iat": int(time.time()),
    }
    return pyjwt.encode(payload, private_key, algorithm="RS256", headers={"kid": "v1"})


@pytest.fixture(autouse=True)
def mock_settings(rsa_keypair):
    _, public_pem = rsa_keypair
    settings = MagicMock()
    settings.supabase_jwt_secret = TEST_SECRET
    settings.supabase_url = "https://test.supabase.co"
    settings.supabase_service_role_key = "test-key"
    settings.redis_url = "redis://localhost:6379"
    settings.fastapi_internal_api_key = "test-api-key"
    settings.stripe_secret_key = ""
    settings.stripe_webhook_secret = ""
    settings.nextauth_secret = ""
    settings.plugin_jwt_public_key = public_pem
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


# ── jti revocation on handshake (audit fix H3) ──


def test_ws_handshake_rejects_revoked_plugin_token(client, rsa_keypair):
    """Plugin token whose jti is server-side revoked must be closed on handshake."""
    from starlette.websockets import WebSocketDisconnect

    private_pem, _ = rsa_keypair
    token = make_plugin_token(jti="jti-revoked", private_key=private_pem)

    with patch("routers.websocket.check_subscription", return_value=True):
        with patch(
            "routers.websocket.is_jti_revoked", AsyncMock(return_value=True)
        ):
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(
                    "/ws", headers={"Authorization": f"Bearer {token}"}
                ) as ws:
                    ws.receive_text()


def test_ws_handshake_accepts_live_plugin_token(client, rsa_keypair):
    """Non-revoked plugin token must pass the handshake check."""
    private_pem, _ = rsa_keypair
    token = make_plugin_token(jti="jti-live", private_key=private_pem)

    with patch("routers.websocket.check_subscription", return_value=True):
        with patch(
            "routers.websocket.is_jti_revoked", AsyncMock(return_value=False)
        ) as check:
            with client.websocket_connect(
                "/ws", headers={"Authorization": f"Bearer {token}"}
            ) as ws:
                ws.send_text(json.dumps({
                    "type": "heartbeat",
                    "id": "hb-1",
                    "payload": {"timestamp": int(time.time())},
                }))
            # The handshake check must have been invoked with our jti.
            call_args = check.call_args
            assert call_args is not None
            assert call_args[0][0] == "jti-live"


def test_ws_handshake_skips_jti_check_for_supabase_token(client):
    """Supabase tokens lack a jti claim — the revocation lookup must be skipped."""
    token = make_token()  # Supabase-style, no jti

    with patch("routers.websocket.check_subscription", return_value=True):
        with patch(
            "routers.websocket.is_jti_revoked", AsyncMock(return_value=True)
        ) as check:
            with client.websocket_connect(
                "/ws", headers={"Authorization": f"Bearer {token}"}
            ) as ws:
                ws.send_text(json.dumps({
                    "type": "heartbeat",
                    "id": "hb-1",
                    "payload": {"timestamp": int(time.time())},
                }))
            # Even though the mock would return True, we must not call it.
            check.assert_not_called()


def test_ws_handshake_lookup_error_closes_socket(client, rsa_keypair):
    """If revocation lookup fails on handshake, fail closed (don't accept the socket).

    Unlike the recheck loop (which preserves existing sessions), handshake
    must fail closed — we never established trust yet.
    """
    from starlette.websockets import WebSocketDisconnect
    from services.jti_revocation import RevocationLookupError

    private_pem, _ = rsa_keypair
    token = make_plugin_token(jti="jti-lookup-err", private_key=private_pem)

    with patch("routers.websocket.check_subscription", return_value=True):
        with patch(
            "routers.websocket.is_jti_revoked",
            AsyncMock(side_effect=RevocationLookupError("supabase down")),
        ):
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(
                    "/ws", headers={"Authorization": f"Bearer {token}"}
                ) as ws:
                    ws.receive_text()
