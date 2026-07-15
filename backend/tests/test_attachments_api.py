import pytest

from tests.conftest import _ceo_headers, _invite_and_join


def _h(j):
    return {"Authorization": f"Bearer {j['access_token']}"}


async def _task_with_two_employees(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])
    e2 = await _invite_and_join(client, ceo_h, "employee", "e2@a.vn", m1["user"]["id"])
    pid = (await client.post("/api/v1/projects", headers=ceo_h, json={"name": "P"})).json()["id"]
    tid = (await client.post("/api/v1/tasks", headers=ceo_h,
                             json={"project_id": pid, "title": "T"})).json()["id"]
    for u in (e1, e2):
        await client.post(f"/api/v1/tasks/{tid}/assignees", headers=ceo_h,
                          json={"user_id": u["user"]["id"]})
    return ceo_h, m1, e1, e2, tid


def _upload_files(name="Hop_dong_A.pdf", content=b"%PDF-fake-bytes"):
    return {"file": (name, content, "application/pdf")}


@pytest.mark.asyncio
async def test_upload_list_download_round_trip(client, storage_dir):
    ceo_h, m1, e1, e2, tid = await _task_with_two_employees(client)
    r = await client.post(f"/api/v1/tasks/{tid}/attachments", headers=_h(e1),
                          files=_upload_files())
    assert r.status_code == 201, r.text
    att = r.json()
    assert att["original_filename"] == "Hop_dong_A.pdf"
    assert att["task_id"] == tid

    listed = await client.get(f"/api/v1/tasks/{tid}/attachments", headers=_h(e2))
    assert len(listed.json()) == 1

    files = list((storage_dir / "attachments").rglob("*.pdf"))
    assert len(files) == 1
    assert "Hop_dong_A" not in files[0].name

    dl = await client.get(f"/api/v1/attachments/{att['id']}/file", headers=_h(e2))
    assert dl.status_code == 200
    assert dl.content == b"%PDF-fake-bytes"


@pytest.mark.asyncio
async def test_upload_rejects_bad_extension(client, storage_dir):
    ceo_h, m1, e1, e2, tid = await _task_with_two_employees(client)
    r = await client.post(f"/api/v1/tasks/{tid}/attachments", headers=_h(e1),
                          files={"file": ("virus.exe", b"x", "application/octet-stream")})
    assert r.status_code == 422
    assert r.json()["detail"] == "unsupported_file_format"


@pytest.mark.asyncio
async def test_outsider_cannot_upload_list_or_download(client, storage_dir):
    ceo_h, m1, e1, e2, tid = await _task_with_two_employees(client)
    m2 = await _invite_and_join(client, ceo_h, "manager", "m2@a.vn")
    r = await client.post(f"/api/v1/tasks/{tid}/attachments", headers=_h(e1),
                          files=_upload_files())
    aid = r.json()["id"]

    assert (await client.post(f"/api/v1/tasks/{tid}/attachments", headers=_h(m2),
                              files=_upload_files())).status_code == 404
    assert (await client.get(f"/api/v1/tasks/{tid}/attachments", headers=_h(m2))).status_code == 404
    assert (await client.get(f"/api/v1/attachments/{aid}/file", headers=_h(m2))).status_code == 404


@pytest.mark.asyncio
async def test_cross_workspace_attachment_404(client, storage_dir):
    ceo_h, m1, e1, e2, tid = await _task_with_two_employees(client)
    r = await client.post(f"/api/v1/tasks/{tid}/attachments", headers=_h(e1),
                          files=_upload_files())
    aid = r.json()["id"]

    other_signup = {
        "workspace_name": "Cong ty B", "email": "ceo-b@a.vn", "password": "secret123",
        "full_name": "Sep B", "device_uuid": "dev-2", "device_name": "",
    }
    resp_signup = await client.post("/api/v1/auth/signup-workspace", json=other_signup)
    assert resp_signup.status_code == 201, resp_signup.text
    other_headers = {"Authorization": f"Bearer {resp_signup.json()['access_token']}"}
    assert (await client.get(f"/api/v1/attachments/{aid}/file",
                             headers=other_headers)).status_code == 404
