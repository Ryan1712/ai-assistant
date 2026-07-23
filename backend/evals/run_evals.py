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
# 120s không đủ: gateway dev (glm-4.7-flash qua beeknoee) có độ trễ dao động rất
# mạnh (quan sát thực tế 2s-134s cho cùng 1 request) — request vẫn "done" thành
# công nhưng runner đã bỏ cuộc và báo "timeout" giả (xem BASELINE.md Phase 1).
POLL_TIMEOUT_S = 200
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

        # 3 task status=todo (mặc định, KHÔNG update lên in_progress) cho Nam Trần —
        # nằm ngoài mục "đang làm" của snapshot (chỉ hiện in_progress, xem
        # snapshot_service.py) để scenario resolve_task-nhầm-lẫn phải thật sự gọi
        # tool mới thấy nhập nhằng, không đọc thẳng từ snapshot ra được.
        nam_tran = self.user_ids["Nam Trần"]
        for title in ("Soạn slide họp khách hàng", "Kiểm tra kho vật tư",
                      "Cập nhật bảng giá quý 3"):
            t = _check(self.http.post("/api/v1/tasks", headers=self._h("ceo"), json={
                "project_id": project["id"], "title": title, "description": ""}),
                f"tạo task {title}")
            _check(self.http.post(f"/api/v1/tasks/{t['id']}/assignees",
                                  headers=self._h("ceo"), json={"user_id": nam_tran}),
                   f"assign Nam Trần {title}")

    def _join(self, role: str, manager_id: str | None, full_name: str, run_id: str) -> str:
        # CEO tạo tài khoản trực tiếp (create_employee) rồi kích hoạt bằng
        # activation_code — không còn luồng signup-invite tự đăng ký cũ (đã xóa,
        # xem plan "feedback fast-track": không có màn hình FE nào redeem token đó).
        slug = full_name.lower().replace(" ", "-").encode("ascii", "ignore").decode() or "nv"
        created = _check(self.http.post("/api/v1/invites", headers=self._h("ceo"), json={
            "email": f"{slug}-{uuid.uuid4().hex[:6]}@smokeco.vn", "full_name": full_name,
            "role": role, "manager_id": manager_id}), f"create employee {full_name}")
        joined = _check(self.http.post("/api/v1/auth/activate", json={
            "code": created["activation_code"], "password": "pw123456",
            "device_uuid": f"d-{uuid.uuid4().hex[:6]}", "device_name": "eval"}),
            f"activate {full_name}")
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
        timeout_s = sc.get("poll_timeout_s", POLL_TIMEOUT_S)
        status, pending_tool, pending_kind = self._poll(conv["id"], req["id"], actor, timeout_s)
        called, route = self._read_traces(req["id"])
        result = grade(sc, called, status, pending_tool, pending_kind, route)
        result.update({"id": sc["id"], "status": status, "called": called,
                       "pending": pending_tool, "pending_kind": pending_kind, "route": route})
        if status == "awaiting_confirmation":
            try:
                # từ chối để không thực sự khóa acc/gửi email trong lúc eval; rồi CHỜ
                # lượt "model nhận user_denied và trả lời" chạy xong — nếu không nó chạy
                # nền song song với scenario kế tiếp, gateway 1-concurrency trả 429.
                # Model có thể xin confirm tool khác → từ chối tiếp, tối đa 3 vòng.
                deny_status = status
                for _ in range(3):
                    if deny_status != "awaiting_confirmation":
                        break
                    self.http.post(f"/api/v1/chat-requests/{req['id']}/confirm",
                                   headers=self._h(actor), json={"approved": False})
                    deny_status, _pending, _kind = self._poll(conv["id"], req["id"], actor, timeout_s)
            except Exception:
                pass  # dọn dẹp best-effort — kết quả chấm đã chốt ở trên
        return result

    def _poll(self, conv_id: str, req_id: str, actor: str,
             timeout_s: float = POLL_TIMEOUT_S) -> tuple[str, str | None, str | None]:
        # timeout_s riêng cho scenario "deep" (Phase 4 §8.2) - ack xong request
        # chuyển deep_running (KHÔNG nằm trong TERMINAL nên vòng lặp cứ chờ tiếp),
        # job nền model_smart+thinking có thể tốn hơn hẳn POLL_TIMEOUT_S mặc định.
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            reqs = _check(self.http.get(f"/api/v1/conversations/{conv_id}/requests",
                                        headers=self._h(actor)), "poll requests")
            me = next((r for r in reqs if r["id"] == req_id), None)
            if me is None:
                time.sleep(POLL_INTERVAL_S)
                continue
            if me["status"] in TERMINAL:
                action = me.get("pending_action") or {}
                return me["status"], action.get("tool_name"), action.get("kind")
            time.sleep(POLL_INTERVAL_S)
        return "timeout", None, None

    def _read_traces(self, req_id: str) -> tuple[list[str], str | None]:
        """Trả (tool đã gọi xuyên suốt mọi dòng trace, route của dòng CUỐI CÙNG
        theo created_at). API đã sort created_at asc nên traces[-1] là dòng mới
        nhất — đường sâu có 2 dòng (ack rồi job), request cần confirm có thể có
        3 dòng (fast rồi confirm rồi fast lần 2) — không được lấy nhầm dòng giữa."""
        for attempt in range(2):
            traces = _check(self.http.get(f"/api/v1/admin/traces/{req_id}",
                                          headers=self._h("ceo")), "đọc trace")
            names = [t["name"] for tr in traces for t in tr["tools_called"]]
            if names or traces or attempt == 1:
                route = traces[-1]["route"] if traces else None
                return names, route
            # status terminal đã visible nhưng dòng trace có thể chưa commit xong
            time.sleep(0.5)
        return [], None


def main() -> int:
    # Console Windows mặc định cp1252 — in tiếng Việt sẽ UnicodeEncodeError.
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--phase", type=int, default=4,
                    help="chạy scenario có phase <= giá trị này (default 4 = phase hiện tại của code)")
    ap.add_argument("--only", default=None, help="chỉ chạy scenario có id này")
    args = ap.parse_args()

    scenarios = []
    for f in sorted((Path(__file__).parent / "scenarios").glob("*.yaml")):
        loaded = yaml.safe_load(f.read_text(encoding="utf-8"))
        scenarios.extend(loaded or [])
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
                  f"pending={r['pending']} pending_kind={r['pending_kind']} route={r['route']}")
            for f_ in r["failures"]:
                print(f"        - {f_}")
    print(f"\nKết quả: {passed} pass / {failed} fail / {skipped} skip "
          f"(tổng {len(scenarios)})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
