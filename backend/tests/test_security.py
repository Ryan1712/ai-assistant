import jwt
import pytest

from app import security


def test_password_hash_roundtrip():
    h = security.hash_password("s3cret")
    assert h != "s3cret"
    assert security.verify_password("s3cret", h)
    assert not security.verify_password("wrong", h)


def test_jwt_roundtrip():
    token = security.create_access_token(user_id="u1", workspace_id="w1", role="ceo")
    payload = security.decode_access_token(token)
    assert payload["sub"] == "u1"
    assert payload["ws"] == "w1"
    assert payload["role"] == "ceo"


def test_jwt_tampered_rejected():
    token = security.create_access_token(user_id="u1", workspace_id="w1", role="ceo")
    with pytest.raises(jwt.InvalidTokenError):
        security.decode_access_token(token + "x")


def test_refresh_token_pair():
    plain, hashed = security.new_refresh_token()
    assert len(plain) >= 32
    assert hashed != plain and len(hashed) == 64  # sha256 hex
