"""JWT validation for WebSocket and HTTP authentication.

Supports two token formats:
1. Plugin JWTs signed by Next.js (iss: "studio-ai", aud: "studio-ai-plugin", userId claim)
2. Supabase JWTs (aud: "authenticated", sub: user_id)

Strategy: peek at unverified claims to choose the right secret, then verify fully.
"""

import jwt
import logging

from config import get_settings

logger = logging.getLogger(__name__)


class JWTValidationError(Exception):
    """Raised when JWT validation fails."""

    def __init__(self, message: str, code: str = "AUTH_FAILED"):
        self.message = message
        self.code = code
        super().__init__(message)


def _is_plugin_token(token: str) -> bool:
    """Peek at unverified claims to determine token type."""
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
        return unverified.get("iss") == "studio-ai" and unverified.get("aud") == "studio-ai-plugin"
    except jwt.DecodeError:
        return False


def validate_jwt(token: str) -> dict:
    """Validate a JWT and return the decoded payload with 'sub' set to the user ID.

    Peeks at unverified claims to choose the right validation path,
    then verifies fully with the appropriate secret.
    """
    settings = get_settings()

    if _is_plugin_token(token):
        return _validate_plugin_token(token, settings.nextauth_secret)

    return _validate_supabase_token(token, settings.supabase_jwt_secret)


def _validate_plugin_token(token: str, secret: str) -> dict:
    """Validate a plugin JWT signed with NEXTAUTH_SECRET."""
    if not secret:
        raise JWTValidationError("NEXTAUTH_SECRET not configured", "SERVER_ERROR")

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer="studio-ai",
            audience="studio-ai-plugin",
        )
    except jwt.ExpiredSignatureError:
        raise JWTValidationError("Token has expired", "TOKEN_EXPIRED")
    except jwt.DecodeError:
        raise JWTValidationError("Token decode failed", "INVALID_TOKEN")
    except jwt.InvalidTokenError as e:
        raise JWTValidationError(f"Invalid token: {e}", "INVALID_TOKEN")

    user_id = payload.get("userId")
    if not user_id:
        raise JWTValidationError("Token missing 'userId' claim", "INVALID_TOKEN")

    # Normalize: set 'sub' for downstream compatibility
    payload["sub"] = user_id
    return payload


def _validate_supabase_token(token: str, secret: str) -> dict:
    """Validate a Supabase JWT."""
    if not secret:
        raise JWTValidationError("JWT secret not configured", "SERVER_ERROR")

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise JWTValidationError("Token has expired", "TOKEN_EXPIRED")
    except jwt.InvalidAudienceError:
        raise JWTValidationError("Invalid audience", "INVALID_AUDIENCE")
    except jwt.DecodeError:
        raise JWTValidationError("Token decode failed", "INVALID_TOKEN")
    except jwt.InvalidTokenError as e:
        raise JWTValidationError(f"Invalid token: {e}", "INVALID_TOKEN")

    user_id = payload.get("sub")
    if not user_id:
        raise JWTValidationError("Token missing 'sub' claim", "INVALID_TOKEN")

    return payload


def extract_user_id(token: str) -> str:
    """Validate JWT and return the user_id (sub claim)."""
    payload = validate_jwt(token)
    return payload["sub"]
