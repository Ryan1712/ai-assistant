import pytest

from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


@pytest.mark.asyncio
async def test_audit_events_rest_round_trip(client):
    ceo_h = await _ceo_headers(client)
    r = await client.get("/api/v1/audit-events", headers=ceo_h)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    # signup-workspace tự tạo 1 LoginEvent qua _log_device — ít nhất 1 event có sẵn
    assert len(body) >= 1
    assert body[0]["type"] == "login"


@pytest.mark.asyncio
async def test_audit_events_403_for_non_ceo(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    r = await client.get("/api/v1/audit-events", headers=_h(m1))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_audit_events_date_filter_query_params(client):
    ceo_h = await _ceo_headers(client)
    r = await client.get("/api/v1/audit-events?date_from=2020-01-01&date_to=2020-01-02",
                         headers=ceo_h)
    assert r.status_code == 200
    assert r.json() == []
