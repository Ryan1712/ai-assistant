import uuid

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.deps import get_bundle_or_user


def _request(headers: dict) -> Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    scope = {"type": "http", "headers": raw_headers}
    return Request(scope)


@pytest.mark.asyncio
async def test_bundle_id_matches_allowlist_returns_fixed_workspace(monkeypatch, db_session):
    from app.config import get_settings
    ws_id = uuid.uuid4()
    monkeypatch.setattr(get_settings(), "public_app_bundle_ids", "com.9learning.app")
    monkeypatch.setattr(get_settings(), "public_report_workspace_id", str(ws_id))

    scope = await get_bundle_or_user(
        request=_request({"x-app-bundle-id": "com.9learning.app"}),
        creds=None, db=db_session)
    assert scope.workspace_id == ws_id
    assert scope.user is None


@pytest.mark.asyncio
async def test_bundle_id_not_in_allowlist_and_no_token_401(monkeypatch, db_session):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "public_app_bundle_ids", "com.9learning.app")
    monkeypatch.setattr(get_settings(), "public_report_workspace_id", str(uuid.uuid4()))

    with pytest.raises(HTTPException) as exc:
        await get_bundle_or_user(
            request=_request({"x-app-bundle-id": "com.other.app"}),
            creds=None, db=db_session)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_feature_disabled_when_allowlist_empty(monkeypatch, db_session):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "public_app_bundle_ids", "")
    monkeypatch.setattr(get_settings(), "public_report_workspace_id", "")

    with pytest.raises(HTTPException) as exc:
        await get_bundle_or_user(
            request=_request({"x-app-bundle-id": "com.9learning.app"}),
            creds=None, db=db_session)
    assert exc.value.status_code == 401
