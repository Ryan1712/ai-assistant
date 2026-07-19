"""Eval harness Phase 0 (spec AI upgrade 4.2) — gọi API THẬT, chấm bằng grader.

Yêu cầu đang chạy: docker compose up -d postgres redis · uvicorn app.main:app ·
arq app.agent.worker.WorkerSettings · ANTHROPIC key thật trong backend/.env.

Chạy:  python -m evals.run_evals [--base-url http://localhost:8000] [--phase 0]
Exit code != 0 nếu có scenario (không bị skip) fail — dùng chặn merge tay.
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

import httpx
import yaml

from evals.grader import grade

TERMINAL = {"done", "awaiting_confirmation", "failed", "cancelled"}
POLL_TIMEOUT_S = 120
POLL_INTERVAL_S = 1.5


def _check(resp: httpx.Response, what: str) -> dict | list:
    if resp.status_code >= 400:
        raise RuntimeError(f"{what} fail: HTTP {resp.status_code} {resp.text[:300]}")
    if not resp.content:
        return {}  # một số endpoint (vd assign task) chủ đích trả body rỗng
    return resp.json()


class EvalClient:
    def __init__(self, base_url: str):
        self.http = httpx.Client(base_url=base_url, timeout=30)
        self.tokens: dict[str, str] = {}   # actor -> access_token
        self.user_ids: dict[str, str] = {}  # tên -> user_id

    def _h(self, actor: str) -> dict:
        return {"Authorization": f"Bearer {self.tokens[actor]}"}

    def seed(self) -> None:
        """Workspace eval mới toanh + nhân sự + project + task cố định cho scenarios."""
        run_id = uuid.uuid4().hex[:8]
        signup = _check(self.http.post("/api/v1/auth/signup-workspace", json={
            "workspace_name": f"Eval {run_id}", "email": f"ceo-{run_id}@smokeco.vn",
            "password": "secret123", "full_name": "Sếp Eval",
            "device_uuid": f"eval-{run_id}", "device_name": "eval"}), "signup ceo")
        self.tokens["ceo"] = signup["access_token"]
        self.user_ids["ceo"] = signup["user"]["id"]

        ha = self._join("manager", None, "Hà Trần", run_id)
        duy = self._join("employee", ha, "Duy Phạm", run_id)
        self._join("employee", ha, "Nam Nguyễn", run_id)
        self._join("employee", ha, "Nam Trần", run_id)

        project = _check(self.http.post("/api/v1/projects", headers=self._h("ceo"),
                                        json={"name": "Marketing Q3",
                                              "goal": "Chiến dịch quý 3"}), "tạo project")
        t1 = _check(self.http.post("/api/v1/tasks", headers=self._h("ceo"), json={
            "project_id": project["id"], "title": "Thiết kế landing page",
            "description": "Landing cho chiến dịch Q3"}), "tạo task 1")
        _check(self.http.post(f"/api/v1/tasks/{t1['id']}/assignees",
                              headers=self._h("ceo"), json={"user_id": duy}), "assign Duy")
        t2 = _check(self.http.post("/api/v1/tasks", headers=self._h("ceo"), json={
            "project_id": project["id"], "title": "Báo cáo doanh thu tháng 6",
            "description": ""}), "tạo task 2")
        _check(self.http.post(f"/api/v1/tasks/{t2['id']}/assignees",
                              headers=self._h("ceo"),
                              json={"user_id": self.user_ids["Nam Nguyễn"]}), "assign Nam")

    def _join(self, role: str, manager_id: str | None, full_name: str, run_id: str) -> str:
        inv = _check(self.http.post("/api/v1/invites", headers=self._h("ceo"),
                                    json={"role": role, "manager_id": manager_id}),
                     f"invite {full_name}")
        slug = full_name.lower().replace(" ", "-").encode("ascii", "ignore").decode() or "nv"
        joined = _check(self.http.post("/api/v1/auth/signup-invite", json={
            "token": inv["token"], "email": f"{slug}-{uuid.uuid4().hex[:6]}@smokeco.vn",
            "password": "pw123456", "full_name": full_name,
            "device_uuid": f"d-{uuid.uuid4().hex[:6]}", "device_name": "eval"}),
            f"join {full_name}")
        self.user_ids[full_name] = joined["user"]["id"]
        # actor "employee" trong scenario = Duy Phạm
        if full_name == "Duy Phạm":
            self.tokens["employee"] = joined["access_token"]
        return joined["user"]["id"]

    def run_scenario(self, sc: dict) -> dict:
        actor = sc.get("actor", "ceo")
        conv = _check(self.http.post("/api/v1/conversations", headers=self._h(actor),
                                     json={"title": f"eval {sc['id']}"}), "tạo conversation")
        req = _check(self.http.post(f"/api/v1/conversations/{conv['id']}/messages",
                                    headers=self._h(actor),
                                    json={"content": sc["user_text"]}), "gửi tin")
        status, pending_tool = self._poll(conv["id"], req["id"], actor)
        called = self._called_tools(req["id"])
        result = grade(sc, called, status, pending_tool)
        result.update({"id": sc["id"], "status": status, "called": called,
                       "pending": pending_tool})
        if status == "awaiting_confirmation":
            # từ chối để không thực sự khóa acc/gửi email trong lúc eval
            self.http.post(f"/api/v1/chat-requests/{req['id']}/confirm",
                           headers=self._h(actor), json={"approved": False})
        return result

    def _poll(self, conv_id: str, req_id: str, actor: str) -> tuple[str, str | None]:
        deadline = time.monotonic() + POLL_TIMEOUT_S
        while time.monotonic() < deadline:
            reqs = _check(self.http.get(f"/api/v1/conversations/{conv_id}/requests",
                                        headers=self._h(actor)), "poll requests")
            me = next((r for r in reqs if r["id"] == req_id), None)
            if me is None:
                time.sleep(POLL_INTERVAL_S)
                continue
            if me["status"] in TERMINAL:
                pending = (me.get("pending_action") or {}).get("tool_name")
                return me["status"], pending
            time.sleep(POLL_INTERVAL_S)
        return "timeout", None

    def _called_tools(self, req_id: str) -> list[str]:
        traces = _check(self.http.get(f"/api/v1/admin/traces/{req_id}",
                                      headers=self._h("ceo")), "đọc trace")
        return [t["name"] for tr in traces for t in tr["tools_called"]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--phase", type=int, default=0,
                    help="chạy scenario có phase <= giá trị này (default 0)")
    ap.add_argument("--only", default=None, help="chỉ chạy scenario có id này")
    args = ap.parse_args()

    scenarios = []
    for f in sorted((Path(__file__).parent / "scenarios").glob("*.yaml")):
        scenarios.extend(yaml.safe_load(f.read_text(encoding="utf-8")))
    if args.only:
        scenarios = [s for s in scenarios if s["id"] == args.only]

    client = EvalClient(args.base_url)
    print("Seed workspace eval...")
    client.seed()

    passed = failed = skipped = 0
    for sc in scenarios:
        if sc.get("phase", 0) > args.phase:
            skipped += 1
            print(f"  SKIP  {sc['id']} (phase {sc['phase']})")
            continue
        try:
            r = client.run_scenario(sc)
        except Exception as exc:  # 1 scenario sap khong duoc lam mat ket qua cac scenario sau
            failed += 1
            print(f"  ERROR {sc['id']}  {type(exc).__name__}: {exc}")
            continue
        if r["passed"]:
            passed += 1
            print(f"  PASS  {r['id']}  status={r['status']} tools={r['called']}")
        else:
            failed += 1
            print(f"  FAIL  {r['id']}  status={r['status']} tools={r['called']} "
                  f"pending={r['pending']}")
            for f_ in r["failures"]:
                print(f"        - {f_}")
    print(f"\nKết quả: {passed} pass / {failed} fail / {skipped} skip "
          f"(tổng {len(scenarios)})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
