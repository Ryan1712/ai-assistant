import pytest

from app.config import Settings, assert_safe_config
from tests.conftest import SIGNUP


@pytest.mark.asyncio
async def test_email_case_insensitive_login(client):
    await client.post("/api/v1/auth/signup-workspace", json={**SIGNUP, "email": "CEO@A.vn"})
    resp = await client.post("/api/v1/auth/login", json={
        "email": "ceo@a.vn", "password": SIGNUP["password"],
        "device_uuid": "d", "device_name": "",
    })
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_duplicate_email_case_insensitive_409(client):
    await client.post("/api/v1/auth/signup-workspace", json=SIGNUP)
    resp = await client.post("/api/v1/auth/signup-workspace",
                             json={**SIGNUP, "email": SIGNUP["email"].upper()})
    assert resp.status_code == 409


def test_prod_config_fail_fast():
    with pytest.raises(RuntimeError):
        assert_safe_config(Settings(env="production"))
    assert_safe_config(Settings(env="production", jwt_secret="x" * 48))  # ok
    assert_safe_config(Settings())  # dev ok


def test_openapi_has_bearer_scheme():
    from app.main import create_app
    spec = create_app().openapi()
    schemes = spec.get("components", {}).get("securitySchemes", {})
    assert any(s.get("scheme") == "bearer" for s in schemes.values())
