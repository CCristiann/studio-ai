"""Tests for JWT validation middleware."""

import time
import jwt as pyjwt
import pytest
from unittest.mock import patch, MagicMock
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from middleware.jwt_validation import validate_jwt, extract_user_id, JWTValidationError

TEST_SECRET = "test-secret-key-for-jwt-validation"
TEST_NEXTAUTH_SECRET = "test-nextauth-secret-for-plugin-tokens"


@pytest.fixture(scope="module")
def rsa_keypair():
    """Generate a fresh RSA keypair once per test module."""
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


def make_plugin_token(
    user_id: str = "user-plugin-1",
    exp_offset: int = 3600,
    alg: str = "RS256",
    key: str = "",
    headers: dict | None = None,
) -> str:
    """Build a Studio AI plugin JWT (RS256 by default; HS256 for legacy tests)."""
    payload = {
        "userId": user_id,
        "jti": "test-jti",
        "iss": "studio-ai",
        "aud": "studio-ai-plugin",
        "exp": int(time.time()) + exp_offset,
        "iat": int(time.time()),
    }
    return pyjwt.encode(payload, key, algorithm=alg, headers=headers or {"kid": "v1"})


@pytest.fixture(autouse=True)
def mock_settings(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    settings = MagicMock()
    settings.supabase_jwt_secret = TEST_SECRET
    settings.nextauth_secret = TEST_NEXTAUTH_SECRET
    settings.plugin_jwt_public_key = public_pem
    settings._private_pem = private_pem  # convenience for tests
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


# ── Plugin token verification (ADR 2026-04-15: RS256 with HS256 cutover compat) ──


def test_plugin_token_rs256_verifies(mock_settings):
    token = make_plugin_token(key=mock_settings._private_pem, alg="RS256")
    payload = validate_jwt(token)
    assert payload["sub"] == "user-plugin-1"
    assert payload["userId"] == "user-plugin-1"


def test_plugin_token_hs256_legacy_verifies(mock_settings):
    """Legacy HS256 plugin tokens must still verify during the cutover window."""
    token = make_plugin_token(
        key=TEST_NEXTAUTH_SECRET, alg="HS256", headers={}
    )
    payload = validate_jwt(token)
    assert payload["sub"] == "user-plugin-1"


def test_plugin_token_rs256_wrong_key_rejected(mock_settings):
    """Token signed by a different RSA key must fail verification."""
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_pem = other.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    token = make_plugin_token(key=other_pem, alg="RS256")
    with pytest.raises(JWTValidationError):
        validate_jwt(token)


def test_plugin_token_hs256_wrong_secret_rejected(mock_settings):
    token = make_plugin_token(key="some-other-secret", alg="HS256", headers={})
    with pytest.raises(JWTValidationError):
        validate_jwt(token)


def test_plugin_token_unsupported_alg_rejected(mock_settings):
    """An attacker substituting alg=none must be rejected."""
    payload = {
        "userId": "evil",
        "jti": "e",
        "iss": "studio-ai",
        "aud": "studio-ai-plugin",
        "exp": int(time.time()) + 3600,
    }
    token = pyjwt.encode(payload, "", algorithm="none")
    with pytest.raises(JWTValidationError, match="Unsupported alg"):
        validate_jwt(token)


def test_plugin_token_rs256_missing_public_key(mock_settings):
    mock_settings.plugin_jwt_public_key = ""
    token = make_plugin_token(key=mock_settings._private_pem, alg="RS256")
    with pytest.raises(JWTValidationError, match="PLUGIN_JWT_PUBLIC_KEY"):
        validate_jwt(token)


def test_plugin_token_expired_rs256(mock_settings):
    token = make_plugin_token(
        key=mock_settings._private_pem, alg="RS256", exp_offset=-3600
    )
    with pytest.raises(JWTValidationError, match="expired"):
        validate_jwt(token)
