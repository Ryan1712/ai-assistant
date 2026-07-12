# Plan 5 — Tính năng mới từ funtional-plan 2026-07-12 (Backend)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bổ sung vào backend các tính năng mới của bản plan 2026-07-12: Instruction (AI hot-reload), Note, Dashboard "Hôm nay", subscription mock Basic/Advanced, self sign-up bằng mã mời workspace, và stub tích hợp cổng báo cáo ceo.9learning.edu.vn.

**Architecture:** Theo đúng pattern hiện có: model trong `app/models.py`, quyền ở service layer (`app/services/*`), REST router dưới `/api/v1`, agent tool đăng ký qua `_register()` trong `app/agent/tools.py`. "Hot reload" Instruction đạt được tự nhiên vì agent loop đọc DB ở mỗi request — chỉ cần build system prompt từ DB thay vì hằng số. Portal 9learning chưa có API spec → dựng client stub bật/tắt bằng config (mặc định mock).

**Tech Stack:** FastAPI async, SQLAlchemy 2.0 async, Pydantic v2, pytest + aiosqlite, alembic.

## Global Constraints (từ CLAUDE.md)

- Mọi bảng mới có `workspace_id`, mọi query lọc theo workspace.
- Quyền kiểm tra ở service layer, actor từ JWT — không từ tham số client/model.
- Route dưới `/api/v1`; đổi contract → chạy `python scripts/export_openapi.py`.
- TDD: test trước, code sau; mỗi task một commit.
- Model LLM từ config, không hardcode.

## Quyết định thiết kế trong plan này

- **Instruction** mirror pattern Skill/SkillVersion: bảng `instructions` (metadata + version hiện tại) + `instruction_versions` (nội dung theo version, immutable log). Chỉ CEO tạo/sửa. Mọi user trong workspace được "hưởng" instruction qua system prompt; chỉ CEO xem/quản lý qua API.
- **Hot reload:** `run_agent_loop` gọi `instruction_service.active_instructions_text(db, workspace_id)` mỗi request → ghép vào SYSTEM_PROMPT. Không cache → cập nhật là áp dụng ngay.
- **Note** là ghi chú cá nhân: ai tạo người đó thấy (CEO cũng không đọc note người khác — note ≠ task update). Gắn optional task/project (phải visible với actor lúc tạo), tags là JSON list string, `note_date` mặc định hôm nay.
- **Dashboard "Hôm nay"** = 1 endpoint đọc-only tổng hợp theo phạm vi quyền sẵn có (`visible_task_ids`): task đến hạn hôm nay, task quá hạn, task in_progress, update mới 24h của đội, note hôm nay của mình + counters.
- **Subscription mock:** cột `plan` trên `workspaces` (basic|advanced, default basic). Giới hạn Basic (hằng số trong `app/plans.py`): 5 projects, 20 skills, 20 users-invite. Tính năng chỉ Advanced: portal 9learning. Chỉ CEO đổi gói (mock, không thanh toán).
- **Mã mời workspace:** cột `invite_code` (8 ký tự, unique toàn hệ thống) trên `workspaces`, sinh lúc tạo workspace. `POST /auth/signup-code` tạo user `role=employee`, `manager_id=None` (CEO gán sau). Giữ nguyên flow invite-token cũ (phụ lục funtional-plan). CEO xem + rotate code.
- **Portal 9learning:** `PortalClient` (httpx) + `MockPortalClient` (dữ liệu mẫu), chọn qua `settings.portal_mock` (default True). CEO-only + gói Advanced. Tool `list_portal_reports`, `get_portal_report` để AI đọc và đối chiếu trong chat; REST tối thiểu cho FE.
- **Root CEO giữ nguyên** (phụ lục plan ghi cần xác nhận product — không đụng).
- **Push notification thật (FCM/Expo)**: để sang Plan 6/7 cùng FE (cần push token từ app). In-app Notification + WS đã có.

---

### Task 1: Instruction — model + service

**Files:**
- Modify: `backend/app/models.py` (thêm `Instruction`, `InstructionVersion`)
- Create: `backend/app/services/instruction_service.py`
- Test: `backend/tests/test_instructions.py`

**Interfaces (Produces):**
```python
class Instruction(Base):  # bảng "instructions"
    id, workspace_id, title: str(255), version: int (default 1),
    created_by: FK users, created_at

class InstructionVersion(Base):  # bảng "instruction_versions", UQ (instruction_id, version)
    id, workspace_id, instruction_id: FK, version: int, content: Text,
    created_by, created_at

# instruction_service:
async def create_instruction(db, actor, title: str, content: str) -> Instruction      # CEO only (403)
async def update_instruction(db, actor, instruction_id, content: str) -> int          # CEO only, bump version, trả version mới; 404 nếu khác workspace
async def list_instructions(db, actor) -> list[dict]                                  # CEO only; dict{id,title,version,content(latest)}
async def delete_instruction(db, actor, instruction_id) -> None                       # CEO only (thu hồi)
async def active_instructions_text(db, workspace_id) -> str                           # KHÔNG check quyền (gọi từ agent loop); ghép "## {title}\n{content}" mọi instruction, "" nếu trống
```

- [x] Test trước: CEO tạo → version 1; update → version 2 và `active_instructions_text` trả nội dung mới; manager/employee gọi create/update/list → 403; workspace khác không thấy; delete xong `active_instructions_text` không còn chứa nội dung.
- [x] Implement + pass + commit `feat(be): instruction model + service`.

### Task 2: Instruction — REST + agent tools + hot reload vào agent loop

**Files:**
- Create: `backend/app/api/instructions.py` (router prefix `/api/v1/instructions`)
- Modify: `backend/app/main.py` (include router), `backend/app/schemas.py` (`InstructionCreateIn{title,content}`, `InstructionUpdateIn{content}`, `InstructionOut{id,title,version,content}`)
- Modify: `backend/app/agent/tools.py` (tools: `create_instruction`, `update_instruction`, `list_instructions`, `delete_instruction` — delete là sensitive)
- Modify: `backend/app/agent/loop.py` (build system prompt: `SYSTEM_PROMPT + "\n\n# Chỉ dẫn từ CEO công ty\n" + text` nếu có)
- Test: `backend/tests/test_instructions_api.py`, mở rộng `backend/tests/test_agent_tools_instructions.py`; test loop dùng fake LLM assert system prompt chứa nội dung instruction mới nhất

**REST:** `POST ""` 201, `GET ""`, `PATCH "/{id}"` (body content → version mới), `DELETE "/{id}"` 204. Tất cả CEO-only.

- [x] Test trước → implement → pass → export openapi → commit `feat(be): instruction REST + agent tools + hot reload system prompt`.

### Task 3: Note — model + service + REST + tools

**Files:**
- Modify: `backend/app/models.py` (`Note`: id, workspace_id, author_id FK users, content Text, tags JSON default list, note_date Date default hôm nay UTC, task_id FK nullable, project_id FK nullable, created_at)
- Create: `backend/app/services/note_service.py`, `backend/app/api/notes.py` (prefix `/api/v1/notes`)
- Modify: `backend/app/schemas.py` (`NoteCreateIn{content, tags?, note_date?, task_id?, project_id?}`, `NoteOut`), `backend/app/main.py`, `backend/app/agent/tools.py` (`create_note`, `list_notes` — filter `date?`, `tag?`)
- Test: `backend/tests/test_notes.py`, `backend/tests/test_agent_tools_notes.py`

**Service:**
```python
async def create_note(db, actor, content, tags=None, note_date=None, task_id=None, project_id=None) -> Note
# task_id/project_id phải visible với actor (404 nếu không); note thuộc workspace actor
async def list_notes(db, actor, on_date=None, tag=None) -> list[Note]  # CHỈ note của chính actor
```

- [x] Test trước: tạo note gắn task visible OK; task không visible → 404; user khác (kể cả CEO) không thấy note của mình; filter theo ngày/tag. → implement → pass → commit `feat(be): note model + service + REST + agent tools`.

### Task 4: Dashboard "Hôm nay"

**Files:**
- Create: `backend/app/services/dashboard_service.py`, `backend/app/api/dashboard.py` (`GET /api/v1/dashboard/today`)
- Modify: `backend/app/schemas.py` (`TodayDashboardOut`), `backend/app/main.py`, `backend/app/agent/tools.py` (tool `get_today_dashboard`)
- Test: `backend/tests/test_dashboard.py`, thêm case tool trong `backend/tests/test_agent_tools_dashboard.py`

**Service:**
```python
async def today_dashboard(db, actor) -> dict:
# {"due_today": [...], "overdue": [...], "in_progress": [...],
#  "recent_updates": [...(update 24h qua trên task visible, kèm task_title, author)],
#  "notes_today": [...note của actor hôm nay],
#  "counters": {"overdue": n, "waiting_on_me": n(task assigned cho actor chưa done), "updates_24h": n}}
# Phạm vi task = visible_task_ids(actor); employee chỉ thấy task mình; manager thấy đội; CEO thấy hết.
```

- [x] Test trước (3 role thấy đúng phạm vi; task quá hạn/đến hạn hôm nay phân loại đúng; note chỉ của mình) → implement → pass → export openapi → commit `feat(be): today dashboard endpoint + tool`.

### Task 5: Subscription mock (Basic/Advanced) + feature gate

**Files:**
- Modify: `backend/app/models.py` (`WorkspacePlan(str,enum)` basic|advanced; `Workspace.plan` default basic)
- Create: `backend/app/plans.py`:
```python
BASIC_LIMITS = {"projects": 5, "skills": 20, "members": 20}
ADVANCED_FEATURES = {"ceo_portal"}
def plan_allows(workspace, feature: str) -> bool
async def enforce_limit(db, workspace, kind: str) -> None  # HTTPException(403, "plan_limit_reached") khi Basic vượt hạn mức
```
- Create: `backend/app/api/subscription.py` (`GET /api/v1/subscription` mọi user; `PATCH /api/v1/subscription` CEO-only, body `{plan}` — mock)
- Modify: `backend/app/services/work_service.py::create_project`, `skill_service.py::create_skill`, `auth_service.py::create_invite` (gọi `enforce_limit`), `backend/app/schemas.py`, `backend/app/main.py`
- Test: `backend/tests/test_subscription.py`

- [x] Test trước: default basic; CEO đổi advanced OK, employee 403; Basic tạo project thứ 6 → 403 `plan_limit_reached`, advanced thì không; invite/skill tương tự. → implement → pass → export openapi → commit `feat(be): subscription mock + plan limits`.

### Task 6: Mã mời workspace — self sign-up

**Files:**
- Modify: `backend/app/models.py` (`Workspace.invite_code: str(16) unique index` — sinh 8 ký tự A-Z0-9 qua `secrets`)
- Modify: `backend/app/services/auth_service.py` (`signup_workspace` sinh code; thêm `signup_with_code(db, invite_code, email, password, full_name, device_uuid, device_name)` → employee, manager_id=None; sai code → 404 `invalid_invite_code`; workspace Basic vượt hạn mức members → 403; `rotate_invite_code(db, actor)` CEO-only)
- Modify: `backend/app/api/auth.py` (`POST /api/v1/auth/signup-code` 201, trả token như signup-invite), `backend/app/api/invites.py` hoặc router workspace: `GET /api/v1/workspace/invite-code` + `POST /api/v1/workspace/invite-code/rotate` (CEO-only)
- Test: `backend/tests/test_signup_code.py`

- [x] Test trước: signup bằng code đúng → 201, user employee đúng workspace, device được log; code sai → 404; sau rotate code cũ chết, code mới sống; employee xem code → 403. → implement → pass → export openapi → commit `feat(be): workspace invite code self-signup`.

### Task 7: Cổng báo cáo CEO 9learning (stub)

**Files:**
- Create: `backend/app/services/portal_service.py`:
```python
class PortalReport(TypedDict): id, title, period, summary, data: dict
class MockPortalClient:   # dữ liệu mẫu 2 báo cáo doanh thu/vận hành
class HttpPortalClient:   # httpx, base_url = settings.portal_base_url (chưa có spec — best effort GET /api/reports)
def get_portal_client() -> ...   # theo settings.portal_mock (default True)
async def list_reports(db, actor) -> list[PortalReport]   # require_ceo + plan_allows("ceo_portal") else 403 "advanced_plan_required"
async def get_report(db, actor, report_id) -> PortalReport
```
- Modify: `backend/app/config.py` (`portal_mock: bool = True`, `portal_base_url: str = "https://ceo.9learning.edu.vn"`)
- Create: `backend/app/api/portal.py` (`GET /api/v1/portal/reports`, `GET /api/v1/portal/reports/{id}`)
- Modify: `backend/app/agent/tools.py` (tools `list_portal_reports`, `get_portal_report` — không sensitive, read-only), `backend/app/main.py`
- Test: `backend/tests/test_portal.py`

- [x] Test trước: CEO + advanced → đọc được mock reports; CEO + basic → 403 advanced_plan_required; manager → 403; tool trả data cho agent. → implement → pass → export openapi → commit `feat(be): 9learning CEO portal stub + tools`.

### Task 8: Migration + tổng kiểm

**Files:**
- Create: `backend/alembic/versions/<hash>_plan5_new_features.py` (autogenerate: instructions, instruction_versions, notes; cột workspaces.plan, workspaces.invite_code)
- Modify: `openapi.json` (export lần cuối)

- [x] `alembic revision --autogenerate` (cần postgres local) hoặc viết tay theo pattern migration đầu; `pytest tests/ -v` toàn bộ xanh; export openapi; commit `chore(be): plan5 migration + openapi refresh`.

## Self-Review
- Spec coverage: Instruction hot-reload (T1–2), Note (T3), Dashboard (T4), Subscription (T5), mã mời (T6), portal (T7) — đủ các mục mới của funtional-plan trừ push notification thật (chủ đích dời sang plan FE, ghi ở Quyết định thiết kế).
- Type consistency: service signatures ghi rõ ở Interfaces; tools bọc service như pattern tools.py hiện có.
