"""jti revocation lookup for plugin JWTs (audit fix H3).

A signature-valid plugin token remains usable for its 24h TTL, so the WSS
endpoint needs to consult the server-side revocation state. This module
provides a Redis-cached wrapper around the Supabase `plugin_tokens.revoked`
column so the lookup is cheap enough to run both on handshake and on a
periodic timer while the socket is open.

Safe default: if the DB has no row for the jti, we treat it as revoked. A
missing row means either the token is older than our persistence record or
something is wrong with issuance — either way, don't trust it.
"""

import httpx

# Redis cache TTL. Kept shorter than the recheck interval (300s) so a
# revocation can't linger in cache for more than one cycle.
CACHE_TTL_SECONDS = 240
CACHE_KEY_PREFIX = "plugin:jti:"
CACHE_VALUE_REVOKED = "revoked"
CACHE_VALUE_VALID = "valid"


class RevocationLookupError(Exception):
    """Raised when we can't determine revocation state (e.g. Supabase outage).

    The handshake path should close the socket with SERVER_ERROR. The
    periodic recheck loop should catch, log, and preserve the existing
    connection so transient upstream failures don't disconnect producers
    mid-session.
    """


def _cache_key(jti: str) -> str:
    return f"{CACHE_KEY_PREFIX}{jti}"


async def is_jti_revoked(jti: str, redis, settings) -> bool:
    """Return True if the token with this jti is revoked (or missing).

    Consults Redis first; falls through to Supabase on miss.
    Raises RevocationLookupError on upstream failure.
    """
    cached = await redis.get(_cache_key(jti))
    if cached == CACHE_VALUE_REVOKED:
        return True
    if cached == CACHE_VALUE_VALID:
        return False

    url = f"{settings.supabase_url}/rest/v1/plugin_tokens"
    params = {"jti": f"eq.{jti}", "select": "revoked"}
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, headers=headers)

    if response.status_code != 200:
        raise RevocationLookupError(
            f"Supabase plugin_tokens query failed: {response.status_code}"
        )

    data = response.json()
    if not data:
        # Safe default: no row means we don't know this token — don't trust it.
        revoked = True
    else:
        revoked = bool(data[0]["revoked"])

    await redis.set(
        _cache_key(jti),
        CACHE_VALUE_REVOKED if revoked else CACHE_VALUE_VALID,
        ex=CACHE_TTL_SECONDS,
    )
    return revoked
