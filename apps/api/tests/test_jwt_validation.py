"""Tests for JWT validation middleware."""

import time
import jwt as pyjwt
import pytest
from unittest.mock import patch, MagicMock

from middleware.jwt_validation import validate_jwt, extract_user_id, JWTValidationError

TEST_SECRET = "test-secret-key-for-jwt-validation"


def make_token(
    sub: str = "user-123",
    email: str = "test@example.com",
    exp_offset: int = 3600,
    aud: str = "authenticated",
    secret: str = TEST_SECRET,
) -> str:
    payload = {
        "sub": sub,
        "email": email,
        "role": "authenticated",
        "aud": aud,
        "exp": int(time.time()) + exp_offset,
    }
    return pyjwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture(autouse=True)
def mock_settings():
    settings = MagicMock()
    settings.supabase_jwt_secret = TEST_SECRET
    with patch("middleware.jwt_validation.get_settings", return_value=settings):
        yield settings


def test_validate_valid_token():
    token = make_token()
    payload = validate_jwt(token)
    assert payload["sub"] == "user-123"
    assert payload["email"] == "test@example.com"
    assert payload["aud"] == "authenticated"


def test_validate_expired_token():
    token = make_token(exp_offset=-3600)
    with pytest.raises(JWTValidationError, match="expired"):
        validate_jwt(token)


def test_validate_wrong_audience():
    token = make_token(aud="wrong-audience")
    with pytest.raises(JWTValidationError, match="audience"):
        validate_jwt(token)


def test_validate_wrong_secret():
    token = make_token(secret="wrong-secret")
    with pytest.raises(JWTValidationError, match="decode failed"):
        validate_jwt(token)


def test_validate_missing_sub():
    payload = {
        "email": "test@example.com",
        "role": "authenticated",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
    }
    token = pyjwt.encode(payload, TEST_SECRET, algorithm="HS256")
    with pytest.raises(JWTValidationError, match="missing 'sub'"):
        validate_jwt(token)


def test_validate_garbage_token():
    with pytest.raises(JWTValidationError):
        validate_jwt("not-a-real-token")


def test_extract_user_id():
    token = make_token(sub="user-456")
    user_id = extract_user_id(token)
    assert user_id == "user-456"


def test_missing_secret(mock_settings):
    mock_settings.supabase_jwt_secret = ""
    token = make_token()
    with pytest.raises(JWTValidationError, match="not configured"):
        validate_jwt(token)
