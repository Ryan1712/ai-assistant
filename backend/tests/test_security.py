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


def test_verify_password_garbage_hash_returns_false():
    assert security.verify_password("anything", "not-a-bcrypt-hash") is False


def test_expired_token_rejected(monkeypatch):
    from datetime import datetime, timedelta, timezone

    class _FrozenPast:
        @staticmethod
        def now(tz=None):
            return datetime.now(timezone.utc) - timedelta(hours=1)

    import app.security as sec
    monkeypatch.setattr(sec, "datetime", _FrozenPast)
    token = security.create_access_token(user_id="u1", workspace_id="w1", role="ceo")
    monkeypatch.undo()
    with pytest.raises(jwt.InvalidTokenError):
        security.decode_access_token(token)


def test_hash_refresh_token_matches_new_refresh_token():
    plain, hashed = security.new_refresh_token()
    assert security.hash_refresh_token(plain) == hashed
