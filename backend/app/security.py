import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_settings


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()


def verify_password(p: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(p.encode(), h.encode())
    except ValueError:
        return False


def create_access_token(*, user_id: str, workspace_id: str, role: str) -> str:
    s = get_settings()
    payload = {
        "sub": user_id,
        "ws": workspace_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=s.access_ttl_minutes),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])


def new_refresh_token() -> tuple[str, str]:
    plain = secrets.token_urlsafe(32)
    return plain, hashlib.sha256(plain.encode()).hexdigest()


def hash_refresh_token(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()
