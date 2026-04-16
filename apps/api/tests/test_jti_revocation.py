"""Tests for jti revocation lookup (audit fix H3).

The WSS endpoint validates a plugin JWT's signature on connect, but a
signature-valid token remains usable for its full 24h TTL even if the user
has revoked it (e.g. lost device, "log out everywhere"). H3 closes that gap:
the relay consults `plugin_tokens.revoked` via a Redis-cached lookup, both on
handshake and on a periodic recheck while the socket is open.

These tests pin the lookup contract. The recheck-loop tests live in
test_websocket.py since they touch the endpoint wiring.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)  # cache miss by default
    r.set = AsyncMock()
    return r


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.supabase_url = "https://test.supabase.co"
    s.supabase_service_role_key = "test-service-role-key"
    return s


def _mock_httpx(response_json, status_code: int = 200):
    """Build an async-context-manager mock for httpx.AsyncClient."""
    response = MagicMock()
    response.status_code = status_code
    response.json = MagicMock(return_value=response_json)

    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


async def test_is_jti_revoked_returns_true_when_db_marks_revoked(
    mock_redis, mock_settings
):
    """Token whose row has revoked=true must be treated as revoked."""
    from services.jti_revocation import is_jti_revoked

    client = _mock_httpx([{"revoked": True}])
    with patch("services.jti_revocation.httpx.AsyncClient", return_value=client):
        result = await is_jti_revoked("jti-abc", mock_redis, mock_settings)

    assert result is True


async def test_is_jti_revoked_returns_false_when_db_marks_valid(
    mock_redis, mock_settings
):
    """Token whose row has revoked=false must be treated as live."""
    from services.jti_revocation import is_jti_revoked

    client = _mock_httpx([{"revoked": False}])
    with patch("services.jti_revocation.httpx.AsyncClient", return_value=client):
        result = await is_jti_revoked("jti-live", mock_redis, mock_settings)

    assert result is False


async def test_is_jti_revoked_treats_missing_row_as_revoked(
    mock_redis, mock_settings
):
    """Safe default: if no row exists for this jti, treat the token as revoked.

    Mirrors the H1 fix for subscriptions — a missing row implies a gap in
    our persistence, and we shouldn't grant access on the basis of absence.
    """
    from services.jti_revocation import is_jti_revoked

    client = _mock_httpx([])  # empty result
    with patch("services.jti_revocation.httpx.AsyncClient", return_value=client):
        result = await is_jti_revoked("jti-unknown", mock_redis, mock_settings)

    assert result is True


async def test_is_jti_revoked_cache_hit_revoked_skips_db(
    mock_redis, mock_settings
):
    """Cache hit with value 'revoked' must skip httpx.

    Keeps the recheck-loop's steady-state cost near zero — with 5min recheck
    interval and 240s cache TTL, almost every recheck sees a cache hit.
    """
    from services.jti_revocation import is_jti_revoked

    mock_redis.get = AsyncMock(return_value="revoked")
    # Any httpx call here would raise AttributeError because the patch is
    # strict — that's the point: we must NOT call it.
    with patch("services.jti_revocation.httpx.AsyncClient") as m:
        result = await is_jti_revoked("jti-cached", mock_redis, mock_settings)

    assert result is True
    mock_redis.get.assert_awaited_once_with("plugin:jti:jti-cached")
    m.assert_not_called()


async def test_is_jti_revoked_cache_hit_valid_skips_db(
    mock_redis, mock_settings
):
    """Cache hit with value 'valid' must return False without hitting httpx."""
    from services.jti_revocation import is_jti_revoked

    mock_redis.get = AsyncMock(return_value="valid")
    with patch("services.jti_revocation.httpx.AsyncClient") as m:
        result = await is_jti_revoked("jti-cached-live", mock_redis, mock_settings)

    assert result is False
    m.assert_not_called()


async def test_is_jti_revoked_miss_writes_revoked_to_cache(
    mock_redis, mock_settings
):
    """On miss + DB says revoked, we must write 'revoked' back with a TTL."""
    from services.jti_revocation import is_jti_revoked, CACHE_TTL_SECONDS

    client = _mock_httpx([{"revoked": True}])
    with patch("services.jti_revocation.httpx.AsyncClient", return_value=client):
        await is_jti_revoked("jti-new", mock_redis, mock_settings)

    mock_redis.set.assert_awaited_once_with(
        "plugin:jti:jti-new", "revoked", ex=CACHE_TTL_SECONDS
    )


async def test_is_jti_revoked_miss_writes_valid_to_cache(
    mock_redis, mock_settings
):
    """On miss + DB says live, we must write 'valid' back with a TTL."""
    from services.jti_revocation import is_jti_revoked, CACHE_TTL_SECONDS

    client = _mock_httpx([{"revoked": False}])
    with patch("services.jti_revocation.httpx.AsyncClient", return_value=client):
        await is_jti_revoked("jti-new-live", mock_redis, mock_settings)

    mock_redis.set.assert_awaited_once_with(
        "plugin:jti:jti-new-live", "valid", ex=CACHE_TTL_SECONDS
    )


async def test_is_jti_revoked_http_error_raises(mock_redis, mock_settings):
    """A non-200 from Supabase must raise RevocationLookupError.

    Raising (rather than returning True or False) lets the handshake path
    close the socket with SERVER_ERROR, while the recheck loop can catch
    and preserve the connection through transient Supabase outages.
    """
    from services.jti_revocation import is_jti_revoked, RevocationLookupError

    client = _mock_httpx([], status_code=500)
    with patch("services.jti_revocation.httpx.AsyncClient", return_value=client):
        with pytest.raises(RevocationLookupError):
            await is_jti_revoked("jti-error", mock_redis, mock_settings)

    # Must NOT poison the cache with a value derived from an error response.
    mock_redis.set.assert_not_called()


# ── Recheck loop (called as a background task by the WSS endpoint) ──


async def test_recheck_loop_closes_ws_on_revoked(mock_redis, mock_settings):
    """When the loop observes revocation, it closes the socket and exits."""
    from routers.websocket import _jti_recheck_loop, WS_CLOSE_AUTH_FAILED

    ws = AsyncMock()
    ws.close = AsyncMock()

    with patch(
        "routers.websocket.is_jti_revoked", AsyncMock(return_value=True)
    ):
        await _jti_recheck_loop(
            ws, "jti-x", mock_redis, mock_settings, interval=0.01
        )

    ws.close.assert_awaited_once()
    _, kwargs = ws.close.call_args
    assert kwargs.get("code") == WS_CLOSE_AUTH_FAILED


async def test_recheck_loop_keeps_socket_alive_on_lookup_error(
    mock_redis, mock_settings
):
    """Transient Supabase outage must NOT disconnect the producer.

    We simulate: two lookup errors, then a 'not revoked' on the third try.
    After the third tick the task is still running — we cancel it and
    verify ws.close was never called.
    """
    import asyncio
    from services.jti_revocation import RevocationLookupError
    from routers.websocket import _jti_recheck_loop

    ws = AsyncMock()
    ws.close = AsyncMock()

    call_count = {"n": 0}

    async def fake_check(jti, redis, settings):
        call_count["n"] += 1
        if call_count["n"] <= 2:
            raise RevocationLookupError("supabase down")
        return False  # eventually recovers

    with patch("routers.websocket.is_jti_revoked", side_effect=fake_check):
        task = asyncio.create_task(
            _jti_recheck_loop(
                ws, "jti-flaky", mock_redis, mock_settings, interval=0.01
            )
        )
        # Let it run through ~4 iterations then cancel.
        await asyncio.sleep(0.08)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert call_count["n"] >= 3, "loop must keep ticking through errors"
    ws.close.assert_not_called()
