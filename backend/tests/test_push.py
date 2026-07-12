import pytest

from app.services import push_service
from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


@pytest.fixture(autouse=True)
def _reset_mock_push():
    push_service.mock_push_client.sent.clear()
    yield
    push_service.mock_push_client.sent.clear()


@pytest.mark.asyncio
async def test_register_push_token_for_own_device(client):
    ceo_h = await _ceo_headers(client)  # signup tạo device "dev-1"
    r = await client.put("/api/v1/devices/push-token", headers=ceo_h,
                         json={"device_uuid": "dev-1", "push_token": "ExponentPushToken[abc]"})
    assert r.status_code == 200, r.text
    # device không tồn tại → 404
    r2 = await client.put("/api/v1/devices/push-token", headers=ceo_h,
                          json={"device_uuid": "khong-co", "push_token": "x"})
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_assign_task_sends_push_to_assignee(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    # m1 đăng ký push token trên device của mình (device_uuid = "d-m1@a.vn")
    await client.put("/api/v1/devices/push-token", headers=_h(m1),
                     json={"device_uuid": "d-m1@a.vn", "push_token": "ExponentPushToken[m1]"})
    p = (await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P"})).json()
    t = (await client.post("/api/v1/tasks", headers=ceo_h,
                           json={"project_id": p["id"], "title": "T"})).json()
    r = await client.post(f"/api/v1/tasks/{t['id']}/assignees", headers=ceo_h,
                          json={"user_id": m1["user"]["id"]})
    assert r.status_code == 201
    sent = push_service.mock_push_client.sent
    assert len(sent) == 1
    tokens, title, body, data = sent[0]
    assert tokens == ["ExponentPushToken[m1]"]
    assert data["type"] == "task_assigned"

    # notification trong DB vẫn được ghi như trước
    notifs = await client.get("/api/v1/users/me", headers=_h(m1))
    assert notifs.status_code == 200


@pytest.mark.asyncio
async def test_push_without_token_is_noop_and_never_raises(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    p = (await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P"})).json()
    t = (await client.post("/api/v1/tasks", headers=ceo_h,
                           json={"project_id": p["id"], "title": "T"})).json()
    r = await client.post(f"/api/v1/tasks/{t['id']}/assignees", headers=ceo_h,
                          json={"user_id": m1["user"]["id"]})
    assert r.status_code == 201  # không token → không push, không lỗi
    assert push_service.mock_push_client.sent == []
