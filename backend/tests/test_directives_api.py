import pytest

from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


async def _directive_from_ceo_to_duy(client):
    ceo_h = await _ceo_headers(client)
    mgr = await _invite_and_join(client, ceo_h, "manager", "ha@a.vn")
    duy = await _invite_and_join(client, ceo_h, "employee", "duy@a.vn", mgr["user"]["id"])
    other = await _invite_and_join(client, ceo_h, "employee", "khac@a.vn", mgr["user"]["id"])
    resp = await client.post("/api/v1/directives", headers=ceo_h,
                             json={"recipient_id": duy["user"]["id"], "verbatim_text": "lam viec X"})
    assert resp.status_code == 201, resp.text
    return ceo_h, _h(duy), _h(other), resp.json()["id"]


@pytest.mark.asyncio
async def test_create_directive_via_rest(client):
    ceo_h, duy_h, other_h, directive_id = await _directive_from_ceo_to_duy(client)

    listed = (await client.get("/api/v1/directives", headers=duy_h)).json()
    assert len(listed) == 1
    assert listed[0]["id"] == directive_id
    assert listed[0]["status"] == "sent"


@pytest.mark.asyncio
async def test_ack_directive_via_rest(client):
    ceo_h, duy_h, other_h, directive_id = await _directive_from_ceo_to_duy(client)

    resp = await client.post(f"/api/v1/directives/{directive_id}/ack", headers=duy_h)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "acked"


@pytest.mark.asyncio
async def test_ack_directive_by_non_recipient_404(client):
    ceo_h, duy_h, other_h, directive_id = await _directive_from_ceo_to_duy(client)

    resp = await client.post(f"/api/v1/directives/{directive_id}/ack", headers=other_h)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_question_directive_via_rest(client):
    ceo_h, duy_h, other_h, directive_id = await _directive_from_ceo_to_duy(client)

    resp = await client.post(f"/api/v1/directives/{directive_id}/question", headers=duy_h,
                             json={"question_text": "Deadline nao?"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "question"
    assert resp.json()["response_text"] == "Deadline nao?"


@pytest.mark.asyncio
async def test_renegotiate_directive_via_rest(client):
    ceo_h, duy_h, other_h, directive_id = await _directive_from_ceo_to_duy(client)

    resp = await client.post(f"/api/v1/directives/{directive_id}/renegotiate", headers=duy_h,
                             json={"new_deadline_proposal": "2026-08-01T00:00:00Z",
                                   "reason": "Ban qua nhieu viec"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "renegotiate"


@pytest.mark.asyncio
async def test_renegotiate_directive_via_rest_reason_only(client):
    ceo_h, duy_h, other_h, directive_id = await _directive_from_ceo_to_duy(client)

    resp = await client.post(f"/api/v1/directives/{directive_id}/renegotiate", headers=duy_h,
                             json={"reason": "Cho toi them 2 ngay"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "renegotiate"
