import json

from scripts.export_openapi import build_openapi


def test_openapi_contains_auth_routes():
    spec = build_openapi()
    paths = spec["paths"]
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/signup-invite" in paths
    assert "/api/v1/users/{user_id}/lock" in paths
    json.dumps(spec)  # serializable
