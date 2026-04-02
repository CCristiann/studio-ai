"""JWT validation for WebSocket and HTTP authentication."""

import jwt
import logging
from datetime import datetime, timezone

from config import get_settings

logger = logging.getLogger(__name__)


class JWTValidationError(Exception):
    """Raised when JWT validation fails."""

    def __init__(self, message: str, code: str = "AUTH_FAILED"):
        self.message = message
        self.code = code
        super().__init__(message)


def validate_jwt(token: str) -> dict:
    """Validate a Supabase JWT and return the decoded payload."""
    settings = get_settings()
    secret = settings.supabase_jwt_secret

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
