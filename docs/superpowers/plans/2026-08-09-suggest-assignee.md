# Gợi ý người phù hợp khi giao task (suggest_assignee) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm trường "chuyên môn" (text tự do, CEO tự nhập) cho nhân viên, và 1 tool `suggest_assignee` để AI gợi ý người phù hợp nhất khi CEO tạo/giao task mà không chỉ rõ người nhận — dựa trên khớp ngữ nghĩa với chuyên môn, tie-break bằng số task đang làm dở.

**Architecture:** Cột mới `User.expertise_notes` (text, nullable) + index vào bảng `embeddings` có sẵn (`source_type="employee_expertise"`, tái dùng nguyên `embedding_service.index_content`/`semantic_search`). Service mới `assignment_service.py` gộp kết quả semantic search với đếm task chưa done. Tool mới `suggest_assignee` (chỉ đọc) + `update_employee_expertise` (CEO sửa chuyên môn sau khi tạo).

**Tech Stack:** Python/FastAPI/SQLAlchemy/Alembic (backend), pytest-asyncio.

## Global Constraints

- KHÔNG dùng chữ "skill" cho bất kỳ field/tool/biến nào liên quan chuyên môn nhân viên — hệ thống đã có `Skill`/`SkillVersion`/`SkillGrant` với nghĩa khác hẳn (tài liệu/kiến thức AI dùng). Dùng "chuyên môn"/`expertise` xuyên suốt.
- Chỉ CEO được sửa `expertise_notes` (`require_ceo`), giống mọi thao tác ghi nhân viên khác.
- `suggest_assignee` KHÔNG tự động gán — chỉ trả gợi ý kèm lý do, CEO vẫn xác nhận qua `propose_actions` bình thường.
- Ngưỡng semantic dùng thẳng `embedding_service.SEMANTIC_SEARCH_MIN_SCORE = 0.15` có sẵn, không tạo hằng số riêng.
- TDD bắt buộc: RED trước, GREEN sau, mỗi task 1 commit.
- **Thêm 2 tool mới → `len(TOOLS)` tăng từ 63 lên 65 → PHẢI cập nhật sentinel ở ĐỦ 11 file test** (đã grep xác nhận): `test_delete_task_project.py`, `test_agent_tools_semantic_search.py`, `test_agent_tools_search.py`, `test_agent_tools_resolver.py`, `test_agent_tools_report_schedule.py`, `test_agent_tools_report.py`, `test_agent_tools_offboard.py`, `test_agent_tools_directive.py`, `test_agent_tools_change_role.py`, `test_agent_tools_analytics.py`, `test_agent_tools_propose_actions.py`. Bỏ sót dù chỉ 1 file sẽ làm full suite fail (bài học đã ghi trong project memory).
- `python scripts/export_openapi.py` chạy sau khi route `/api/v1/employees` đổi schema (Task 1).

---

### Task 1: Model `User.expertise_notes` + migration + mở rộng `add_employee`

**Files:**
- Modify: `backend/app/models.py` (class `User`, sau `notification_prefs` dòng ~70)
- Modify: `backend/app/schemas.py` (`AddEmployeeIn`, `AddEmployeeOut`, `UserOut` — dòng ~38-99)
- Modify: `backend/app/services/auth_service.py` (`add_employee`, dòng ~215-236)
- Modify: `backend/app/agent/tools.py` (`AddEmployeeToolIn`, `_add_employee`, dòng ~367-396)
- Create: migration Alembic mới qua `alembic revision --autogenerate`
- Test: `backend/tests/test_employee_expertise_notes.py` (mới)

**Interfaces:**
- Produces: `User.expertise_notes: str | None` — dùng ở Task 2 (index embedding), Task 3 (service gợi ý), Task 4 (tool `update_employee_expertise`).
- `auth_service.add_employee(db, *, actor, full_name, email=None, expertise_notes=None) -> User` — tham số mới `expertise_notes`, optional, giữ nguyên chữ ký cũ tương thích ngược.

- [ ] **Step 1: Viết test thất bại cho model + `add_employee` nhận `expertise_notes`**

```python
# backend/tests/test_employee_expertise_notes.py
"""suggest_assignee (spec docs/superpowers/specs/2026-08-09-suggest-assignee-design.md):
User.expertise_notes là chuyên môn nhân viên (text tự do, CEO tự nhập) --
KHÔNG liên quan gì tới bảng Skill (tài liệu/kiến thức AI dùng khi trả lời),
tên field cố ý tránh chữ "skill" để không gây nhầm lẫn 2 khái niệm."""
import pytest

from tests.conftest import _ceo_headers


@pytest.mark.asyncio
async def test_add_employee_with_expertise_notes(client):
    ceo_h = await _ceo_headers(client)
    resp = await client.post("/api/v1/employees", headers=ceo_h,
                             json={"full_name": "Duy Linh",
                                   "expertise_notes": "design, figma, frontend react"})
    assert resp.status_code == 201
    assert resp.json()["expertise_notes"] == "design, figma, frontend react"


@pytest.mark.asyncio
async def test_add_employee_without_expertise_notes_defaults_none(client):
    ceo_h = await _ceo_headers(client)
    resp = await client.post("/api/v1/employees", headers=ceo_h,
                             json={"full_name": "No Expertise Guy"})
    assert resp.status_code == 201
    assert resp.json()["expertise_notes"] is None


@pytest.mark.asyncio
async def test_list_users_includes_expertise_notes(client):
    ceo_h = await _ceo_headers(client)
    await client.post("/api/v1/employees", headers=ceo_h,
                      json={"full_name": "Duy Linh", "expertise_notes": "backend python"})
    listed = (await client.get("/api/v1/users", headers=ceo_h)).json()
    duy = next(u for u in listed if u["full_name"] == "Duy Linh")
    assert duy["expertise_notes"] == "backend python"
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && python -m pytest tests/test_employee_expertise_notes.py -v`
Expected: FAIL — `KeyError: 'expertise_notes'` hoặc `422` (field chưa tồn tại trong schema `AddEmployeeIn`).

- [ ] **Step 3: Thêm cột `expertise_notes` vào model `User`**

Trong `backend/app/models.py`, class `User`, thêm sau dòng `notification_prefs`:

```python
    # Chuyên môn nhân viên (text tự do, CEO tự nhập/sửa) -- dùng cho tool
    # suggest_assignee gợi ý người phù hợp khi giao task. KHÔNG liên quan gì
    # tới bảng Skill/SkillVersion (tài liệu/kiến thức AI dùng khi trả lời,
    # có version/cấp quyền) -- 2 khái niệm khác nhau hoàn toàn, tên field cố
    # ý tránh chữ "skill" để không gây nhầm lẫn.
    expertise_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Xác nhận `Text` đã import ở đầu `models.py` (grep `from sqlalchemy import` — đã thấy `Text` dùng ở nhiều model khác trong file như `Project.goal`, chắc chắn đã có sẵn).

- [ ] **Step 4: Cập nhật schema `AddEmployeeIn`/`AddEmployeeOut`/`UserOut`**

Trong `backend/app/schemas.py`:

```python
class AddEmployeeIn(BaseModel):
    full_name: str
    email: EmailStr | None = None
    expertise_notes: str | None = None


class AddEmployeeOut(BaseModel):
    user_id: uuid.UUID
    full_name: str
    email: str | None = None
    expertise_notes: str | None = None
```

Và `UserOut` (dòng ~38-46), thêm field:

```python
class UserOut(BaseModel):
    id: uuid.UUID
    email: str | None
    full_name: str
    role: str
    is_root: bool
    manager_id: uuid.UUID | None
    status: str
    expertise_notes: str | None = None

    model_config = {"from_attributes": True}
```

- [ ] **Step 5: Cập nhật `auth_service.add_employee`**

```python
async def add_employee(db: AsyncSession, *, actor: User, full_name: str,
                       email: str | None = None,
                       expertise_notes: str | None = None) -> User:
    """Thêm 1 người vào DANH SÁCH NHÂN VIÊN công ty (chỉ CEO) — record chỉ để gán
    việc, KHÔNG phải tạo tài khoản. Không mật khẩu (password_hash=None) nên
    login() (Task 1) luôn từ chối — người này không bao giờ đăng nhập app được.
    Sản phẩm quyết định 2026-07-26: chỉ CEO dùng app; xem
    docs/superpowers/specs/2026-07-26-employee-as-list-design.md.
    expertise_notes (2026-08-09): chuyên môn tự do CEO nhập, dùng cho
    suggest_assignee — xem docs/superpowers/specs/2026-08-09-suggest-assignee-design.md."""
    require_ceo(actor)
    await plans.enforce_limit(db, actor.workspace_id, "members")
    email = email.strip().lower() if email else None
    if email and (await db.execute(
            select(User).where(User.email == email))).scalar_one_or_none():
        raise HTTPException(409, "email_taken")
    user = User(workspace_id=actor.workspace_id, email=email, password_hash=None,
               full_name=full_name, role=Role.employee, status=UserStatus.active,
               expertise_notes=expertise_notes.strip() if expertise_notes else None)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "email_taken")
    return user
```

- [ ] **Step 6: Cập nhật route `/api/v1/employees` và tool `add_employee`**

`backend/app/api/invites.py` (route `add_employee`), truyền thêm tham số:

```python
@employees_router.post("", response_model=AddEmployeeOut, status_code=201)
async def add_employee(
    body: AddEmployeeIn,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user = await auth_service.add_employee(
        db, actor=actor, full_name=body.full_name, email=body.email,
        expertise_notes=body.expertise_notes)
    return AddEmployeeOut(user_id=user.id, full_name=user.full_name, email=user.email,
                          expertise_notes=user.expertise_notes)
```

`backend/app/agent/tools.py`, đọc trước dòng thật (số dòng có thể lệch):

```bash
grep -n "class AddEmployeeToolIn" -A 3 backend/app/agent/tools.py
grep -n "async def _add_employee" -A 5 backend/app/agent/tools.py
```

Đổi `AddEmployeeToolIn`:

```python
class AddEmployeeToolIn(BaseModel):
    full_name: str
    email: EmailStr | None = None
    expertise_notes: str | None = None
```

Đổi `_add_employee`:

```python
async def _add_employee(db, actor, body: AddEmployeeToolIn) -> dict:
    user = await auth_service.add_employee(
        db, actor=actor, full_name=body.full_name, email=body.email,
        expertise_notes=body.expertise_notes)
    return {"user_id": str(user.id), "full_name": user.full_name, "email": user.email,
           "note": f"Đã thêm {user.full_name} vào danh sách nhân viên công ty."}
```

Cập nhật tool description `add_employee` (đọc nguyên văn hiện tại trước khi sửa — đã có nội dung dài về cú pháp `$result[N].field` từ đợt fix trước, KHÔNG xóa phần đó) — thêm 1 câu ở cuối:

```bash
grep -n "_register(\"add_employee\"" -A 12 backend/app/agent/tools.py
```

Thêm vào cuối chuỗi mô tả (trước dấu phẩy đóng, trước `AddEmployeeToolIn, _add_employee)`):

```
" Có thể kèm expertise_notes (chuyên môn nhân viên, text tự do vd 'design, "
"figma') nếu CEO có nhắc tới — dùng cho suggest_assignee sau này gợi ý người "
"phù hợp khi giao task. KHÔNG liên quan Skill (tài liệu công ty)."
```

- [ ] **Step 7: Sinh migration Alembic**

Đảm bảo Postgres dev đang chạy (`docker compose up -d postgres redis` ở `backend/`):

```bash
cd backend
.venv\Scripts\activate
alembic revision --autogenerate -m "add expertise_notes to users"
```

Đọc file sinh ra, xác nhận CHỈ có `op.add_column('users', sa.Column('expertise_notes', sa.Text(), nullable=True))` — không có diff thừa nào khác (nếu có, dừng lại kiểm tra drift DB dev trước khi tiếp, theo bài học các lần trước).

- [ ] **Step 8: Áp migration, verify**

```bash
alembic upgrade head
```

Verify: `docker compose exec postgres psql -U app -d app -c "\d users"` — cột `expertise_notes` (text, nullable) phải xuất hiện.

- [ ] **Step 9: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_employee_expertise_notes.py -v`
Expected: PASS cả 3 test.

- [ ] **Step 10: Chạy test liên quan để đảm bảo không phá gì**

Run: `cd backend && python -m pytest tests/test_add_employee_api.py tests/test_users_api.py -v`
Expected: PASS toàn bộ (test cũ không set `expertise_notes` vẫn phải qua vì field optional).

- [ ] **Step 11: Export lại openapi.json**

```bash
python scripts/export_openapi.py
```

- [ ] **Step 12: Commit**

```bash
git add backend/app/models.py backend/app/schemas.py backend/app/services/auth_service.py backend/app/api/invites.py backend/app/agent/tools.py backend/alembic/versions/*.py backend/tests/test_employee_expertise_notes.py openapi.json
git commit -m "feat(employee): them truong expertise_notes (chuyen mon, text tu do CEO nhap)"
```

---

### Task 2: Index chuyên môn vào embedding + tool `update_employee_expertise`

**Files:**
- Modify: `backend/app/services/embedding_service.py` (`VALID_SOURCE_TYPES`, `_RAG_LABELS`, thêm hàm mới)
- Modify: `backend/app/services/auth_service.py` (thêm hàm `update_employee_expertise`)
- Modify: `backend/app/agent/tools.py` (tool mới `update_employee_expertise`, thêm vào `TOOL_GROUPS["admin"]`)
- Test: `backend/tests/test_employee_expertise_notes.py` (mở rộng)
- Test: 11 file sentinel `len(TOOLS) ==` (cập nhật số — xem Global Constraints)

**Interfaces:**
- Consumes: `User.expertise_notes` (Task 1), `embedding_service.index_content` (đã có sẵn).
- Produces: `embedding_service.index_employee_expertise(db, workspace_id, user) -> None`, `auth_service.update_employee_expertise(db, *, actor, user_id, expertise_notes) -> User` — dùng ở Task 3 (semantic_search source_type mới), tool mới ở task này.

- [ ] **Step 1: Viết test thất bại cho index + update**

Đọc `backend/tests/test_embedding_service.py` trước để lấy đúng pattern test `index_content`/`semantic_search` hiện có (fixture `db_session`, cách mock embedding client nếu có).

```bash
grep -n "async def test_" backend/tests/test_embedding_service.py | head -10
```

```python
# thêm vào backend/tests/test_employee_expertise_notes.py
from sqlalchemy import select

from app.models import Embedding, Role, User, Workspace
from app.services import auth_service, embedding_service


@pytest.mark.asyncio
async def test_index_employee_expertise_creates_embedding(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    user = User(workspace_id=ws.id, full_name="Duy Linh", role=Role.employee,
               expertise_notes="design, figma, frontend react")
    db_session.add(user)
    await db_session.commit()

    await embedding_service.index_employee_expertise(db_session, ws.id, user)

    row = (await db_session.execute(select(Embedding).where(
        Embedding.source_type == "employee_expertise", Embedding.source_id == user.id
    ))).scalar_one_or_none()
    assert row is not None
    assert row.content == "design, figma, frontend react"


@pytest.mark.asyncio
async def test_index_employee_expertise_skips_when_none(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    user = User(workspace_id=ws.id, full_name="No Expertise", role=Role.employee,
               expertise_notes=None)
    db_session.add(user)
    await db_session.commit()

    await embedding_service.index_employee_expertise(db_session, ws.id, user)

    row = (await db_session.execute(select(Embedding).where(
        Embedding.source_type == "employee_expertise", Embedding.source_id == user.id
    ))).scalar_one_or_none()
    assert row is None


@pytest.mark.asyncio
async def test_update_employee_expertise_reindexes(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.flush()
    emp = User(workspace_id=ws.id, full_name="Duy Linh", role=Role.employee,
              expertise_notes="design")
    db_session.add(emp)
    await db_session.commit()
    await embedding_service.index_employee_expertise(db_session, ws.id, emp)

    updated = await auth_service.update_employee_expertise(
        db_session, actor=ceo, user_id=emp.id, expertise_notes="backend python")

    assert updated.expertise_notes == "backend python"
    row = (await db_session.execute(select(Embedding).where(
        Embedding.source_type == "employee_expertise", Embedding.source_id == emp.id
    ))).scalar_one()
    assert row.content == "backend python"


@pytest.mark.asyncio
async def test_update_employee_expertise_requires_ceo(db_session):
    from fastapi import HTTPException

    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    manager = User(workspace_id=ws.id, email="m@a.vn", password_hash="x", full_name="M",
                   role=Role.manager)
    emp = User(workspace_id=ws.id, full_name="E", role=Role.employee)
    db_session.add_all([manager, emp])
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await auth_service.update_employee_expertise(
            db_session, actor=manager, user_id=emp.id, expertise_notes="x")
    assert exc.value.status_code == 403
```

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && python -m pytest tests/test_employee_expertise_notes.py -v -k "index_employee or update_employee"`
Expected: FAIL — `AttributeError: module 'app.services.embedding_service' has no attribute 'index_employee_expertise'`.

- [ ] **Step 3: Thêm `"employee_expertise"` vào `VALID_SOURCE_TYPES` + `_RAG_LABELS`**

```bash
grep -n "VALID_SOURCE_TYPES\|_RAG_LABELS = " backend/app/services/embedding_service.py
```

Đổi:

```python
_RAG_LABELS = {"note": "ghi chú", "task_update": "cập nhật task",
              "comment": "bình luận", "chat_message": "hội thoại trước",
              "voice_transcript": "ghi âm", "skill": "skill",
              "employee_expertise": "chuyên môn nhân viên"}

VALID_SOURCE_TYPES: frozenset[str] = frozenset(
    {"note", "task_update", "comment", "chat_message", "voice_transcript", "skill",
     "employee_expertise"})
```

(khớp đúng cú pháp/biến thật đọc được ở bước grep — file thật có thể format khác đôi chút).

- [ ] **Step 4: Thêm hàm `index_employee_expertise`**

Thêm vào cuối `backend/app/services/embedding_service.py` (sau `build_rag_context_block` hoặc cuối file — vị trí không quan trọng, giữ style hiện có):

```python
async def index_employee_expertise(db: AsyncSession, workspace_id: uuid.UUID,
                                    user: "User") -> None:
    """suggest_assignee (2026-08-09): index chuyên môn nhân viên vào bảng
    embeddings chung — tái dùng index_content (upsert thật: nội dung trùng bỏ
    qua, khác thì update tại chỗ, đúng nhu cầu vì expertise_notes CÓ THỂ sửa
    nhiều lần qua update_employee_expertise, giống case voice_transcript)."""
    await index_content(db, workspace_id, "employee_expertise", user.id,
                        user.expertise_notes or "")
```

Cần thêm `_candidates_employee_expertise` và đăng ký vào `_CANDIDATE_FNS` để `semantic_search(source_types=["employee_expertise"])` hoạt động (Task 3 sẽ gọi qua đây) — thêm ngay bây giờ để đồng bộ với các `_candidates_*` khác:

```bash
grep -n "async def _candidates_skill" -A 15 backend/app/services/embedding_service.py
grep -n "^from app.models import" backend/app/services/embedding_service.py
```

Xác nhận `User` đã import trong `embedding_service.py` (đọc dòng import — nếu chưa có, thêm `User` vào danh sách import từ `app.models`). Thêm hàm (theo đúng pattern `_candidates_skill` đọc được ở lệnh grep trên, điều chỉnh cho đúng bảng `User`):

```python
async def _candidates_employee_expertise(db: AsyncSession, actor: User) -> list[tuple[dict, list[float]]]:
    rows = await db.execute(
        select(User, Embedding).join(
            Embedding, and_(Embedding.source_type == "employee_expertise",
                            Embedding.source_id == User.id))
        .where(User.workspace_id == actor.workspace_id))
    return [({"source_type": "employee_expertise", "source_id": str(u.id),
             "content": _snippet(e.content), "full_name": u.full_name}, e.embedding)
            for u, e in rows.all()]
```

Đăng ký vào `_CANDIDATE_FNS`:

```bash
grep -n "_CANDIDATE_FNS = {" -A 10 backend/app/services/embedding_service.py
```

Thêm dòng `"employee_expertise": _candidates_employee_expertise,` vào dict đó (khớp đúng cú pháp thật).

- [ ] **Step 5: Thêm `auth_service.update_employee_expertise`**

Trong `backend/app/services/auth_service.py`, thêm sau `add_employee`:

```python
async def update_employee_expertise(db: AsyncSession, *, actor: User, user_id: uuid_mod.UUID,
                                     expertise_notes: str | None) -> User:
    """CEO sửa chuyên môn nhân viên sau khi đã tạo — re-index embedding ngay
    (cùng pattern edit_request re-index, PO audit 2026-08-08) để
    suggest_assignee luôn dùng nội dung MỚI, không phải bản cũ trước khi sửa."""
    require_ceo(actor)
    user = await db.get(User, user_id)
    if user is None or user.workspace_id != actor.workspace_id:
        raise HTTPException(404, "user_not_found")
    user.expertise_notes = expertise_notes.strip() if expertise_notes else None
    await db.commit()
    from app.services import embedding_service
    await embedding_service.index_employee_expertise(db, actor.workspace_id, user)
    return user
```

(import `embedding_service` cục bộ trong hàm để tránh vòng lặp import nếu `embedding_service.py` từng import ngược từ `auth_service.py` — kiểm tra bằng `grep -n "^from app.services" backend/app/services/embedding_service.py`; nếu không có rủi ro vòng lặp, chuyển import lên đầu file cho nhất quán style).

- [ ] **Step 6: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_employee_expertise_notes.py -v`
Expected: PASS toàn bộ (7 test: 3 từ Task 1 + 4 mới).

- [ ] **Step 7: Thêm tool `update_employee_expertise`**

Trong `backend/app/agent/tools.py`, thêm gần `_add_employee`/`AddEmployeeToolIn`:

```python
class UpdateEmployeeExpertiseToolIn(BaseModel):
    user_id: uuid.UUID
    expertise_notes: str | None = None


async def _update_employee_expertise(db, actor, body: UpdateEmployeeExpertiseToolIn) -> dict:
    user = await auth_service.update_employee_expertise(
        db, actor=actor, user_id=body.user_id, expertise_notes=body.expertise_notes)
    return {"user_id": str(user.id), "full_name": user.full_name,
           "expertise_notes": user.expertise_notes}
```

Đăng ký (đặt ngay sau `_register("add_employee", ...)`):

```python
_register("update_employee_expertise",
          "Sửa chuyên môn (text tự do, vd 'design, figma') của 1 nhân viên đã có "
          "trong danh sách (chỉ CEO). Chuyên môn KHÁC HẲN Skill (tài liệu công ty) "
          "— dùng cho suggest_assignee gợi ý người phù hợp khi giao task. Truyền "
          "expertise_notes=null để xóa/bỏ trống chuyên môn hiện có.",
          UpdateEmployeeExpertiseToolIn, _update_employee_expertise)
```

Thêm `"update_employee_expertise"` vào `TOOL_GROUPS["admin"]` (cùng nhóm `add_employee`):

```bash
grep -n '"admin": frozenset' -A 4 backend/app/agent/tools.py
```

Đổi dòng đó thêm tên tool mới vào set.

- [ ] **Step 8: Cập nhật sentinel `len(TOOLS)` — hiện tại +1 tool (63 → 64), sẽ +1 nữa ở Task 3 (64 → 65)**

Run: `cd backend && grep -rln "len(TOOLS) ==" tests/`

Với TỪNG file trong 11 file đã liệt kê ở Global Constraints, đổi `len(TOOLS) == 63` thành `len(TOOLS) == 64`, và thêm comment nối vào cuối dòng comment cũ (giữ nguyên comment cũ, chỉ nối thêm):

```python
assert len(TOOLS) == 64  # ... (giữ nguyên comment cũ) ... +update_employee_expertise
```

- [ ] **Step 9: Chạy full suite backend**

Run: `cd backend && python -m pytest tests/ -q`
Expected: PASS toàn bộ, không regression (baseline trước task: 868 passed, 0 failed, 4 skipped + 7 test mới Task 1/2 = kỳ vọng ~875 passed).

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/embedding_service.py backend/app/services/auth_service.py backend/app/agent/tools.py backend/tests/test_employee_expertise_notes.py backend/tests/test_delete_task_project.py backend/tests/test_agent_tools_semantic_search.py backend/tests/test_agent_tools_search.py backend/tests/test_agent_tools_resolver.py backend/tests/test_agent_tools_report_schedule.py backend/tests/test_agent_tools_report.py backend/tests/test_agent_tools_offboard.py backend/tests/test_agent_tools_directive.py backend/tests/test_agent_tools_change_role.py backend/tests/test_agent_tools_analytics.py backend/tests/test_agent_tools_propose_actions.py
git commit -m "feat(employee): index chuyen mon vao embedding, tool update_employee_expertise"
```

---

### Task 3: Service `assignment_service.suggest_assignee` + tool + system prompt

**Files:**
- Create: `backend/app/services/assignment_service.py`
- Modify: `backend/app/agent/tools.py` (tool mới `suggest_assignee`, thêm vào `TOOL_GROUPS["work"]`)
- Modify: `backend/app/agent/loop.py` (system prompt — hướng dẫn khi nào gọi `suggest_assignee`)
- Test: `backend/tests/test_assignment_service.py` (mới)
- Test: `backend/tests/test_agent_tools_assignment.py` (mới)
- Test: 11 file sentinel `len(TOOLS) ==` (cập nhật số lần nữa: 64 → 65)

**Interfaces:**
- Consumes: `User.expertise_notes` (Task 1), `embedding_service.semantic_search` (có sẵn, giờ hỗ trợ `source_types=["employee_expertise"]` nhờ Task 2), `permissions.visible_task_ids`, `permissions.require_ceo`.
- Produces: `assignment_service.suggest_assignee(db, actor, *, task_title, task_description="") -> dict` — trả `{"suggestions": [{"user_id": str, "full_name": str, "reason": str}, ...]}` hoặc `{"suggestions": [], "note": str}` khi workspace chưa có nhân viên nào.

- [ ] **Step 1: Viết test thất bại cho `assignment_service.suggest_assignee`**

Đọc `backend/tests/test_embedding_service.py` để xác nhận `MockEmbeddingClient`/cách test không cần API key thật (nếu có `embedding_mock` setting) trước khi viết test dùng semantic search thật.

```bash
grep -n "embedding_mock\|MockEmbedding\|monkeypatch.*embed" backend/tests/test_embedding_service.py backend/app/config.py | head -10
```

```python
# backend/tests/test_assignment_service.py
"""suggest_assignee (spec docs/superpowers/specs/2026-08-09-suggest-assignee-design.md):
gợi ý người phù hợp khi giao task, ưu tiên khớp chuyên môn ngữ nghĩa, tie-break
bằng số task đang làm dở (ít hơn = rảnh hơn). Fallback về người rảnh nhất
toàn workspace nếu không ai khớp chuyên môn."""
import pytest

from app.models import Project, Role, Task, TaskAssignee, TaskStatus, User, Workspace
from app.services import assignment_service, auth_service, embedding_service


async def _mk_ceo(db, ws):
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    return ceo


async def _mk_employee_with_expertise(db, ws, name, expertise):
    user = User(workspace_id=ws.id, full_name=name, role=Role.employee,
               expertise_notes=expertise)
    db.add(user)
    await db.flush()
    await embedding_service.index_employee_expertise(db, ws.id, user)
    return user


@pytest.mark.asyncio
async def test_suggest_assignee_khop_dung_chuyen_mon(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = await _mk_ceo(db_session, ws)
    designer = await _mk_employee_with_expertise(
        db_session, ws, "Duy Linh", "design, figma, giao dien nguoi dung")
    backend_dev = await _mk_employee_with_expertise(
        db_session, ws, "Nam", "backend python, database, api")
    await db_session.commit()

    result = await assignment_service.suggest_assignee(
        db_session, ceo, task_title="Thiet ke lai giao dien trang chu",
        task_description="Can lam moi UI/UX trang chu bang Figma")

    assert len(result["suggestions"]) >= 1
    top = result["suggestions"][0]
    assert top["user_id"] == str(designer.id)
    assert "Duy Linh" in top["reason"] or top["full_name"] == "Duy Linh"


@pytest.mark.asyncio
async def test_suggest_assignee_tie_break_bang_so_task_dang_lam(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = await _mk_ceo(db_session, ws)
    busy = await _mk_employee_with_expertise(db_session, ws, "Busy Dev", "python backend api")
    free = await _mk_employee_with_expertise(db_session, ws, "Free Dev", "python backend api")
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    # busy có 3 task dang lam, free co 0
    for i in range(3):
        t = Task(workspace_id=ws.id, project_id=project.id, title=f"T{i}",
                 status=TaskStatus.in_progress, created_by=ceo.id)
        db_session.add(t)
        await db_session.flush()
        db_session.add(TaskAssignee(workspace_id=ws.id, task_id=t.id, user_id=busy.id))
    await db_session.commit()

    result = await assignment_service.suggest_assignee(
        db_session, ceo, task_title="Viet API moi", task_description="backend python")

    top_ids = [s["user_id"] for s in result["suggestions"][:2]]
    assert str(free.id) in top_ids
    # free phải đứng trước busy nếu cả 2 cùng lọt top (score gần bằng nhau)
    if str(busy.id) in top_ids:
        assert top_ids.index(str(free.id)) < top_ids.index(str(busy.id))


@pytest.mark.asyncio
async def test_suggest_assignee_fallback_khi_khong_ai_khop_chuyen_mon(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = await _mk_ceo(db_session, ws)
    emp1 = await _mk_employee_with_expertise(db_session, ws, "E1", "ke toan")
    project = Project(workspace_id=ws.id, name="P", created_by=ceo.id)
    db_session.add(project)
    await db_session.flush()
    t = Task(workspace_id=ws.id, project_id=project.id, title="T",
             status=TaskStatus.in_progress, created_by=ceo.id)
    db_session.add(t)
    await db_session.flush()
    db_session.add(TaskAssignee(workspace_id=ws.id, task_id=t.id, user_id=emp1.id))
    emp2 = await _mk_employee_with_expertise(db_session, ws, "E2", "hanh chinh")
    await db_session.commit()

    result = await assignment_service.suggest_assignee(
        db_session, ceo, task_title="Thiet ke he thong machine learning phuc tap",
        task_description="AI, deep learning, neural network")

    assert len(result["suggestions"]) == 1
    # emp2 ranh hon (0 task) nen duoc chon lam fallback
    assert result["suggestions"][0]["user_id"] == str(emp2.id)
    assert "ranh" in result["suggestions"][0]["reason"].lower()


@pytest.mark.asyncio
async def test_suggest_assignee_requires_ceo(db_session):
    from fastapi import HTTPException

    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    manager = User(workspace_id=ws.id, email="m@a.vn", password_hash="x", full_name="M",
                   role=Role.manager)
    db_session.add(manager)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await assignment_service.suggest_assignee(db_session, manager, task_title="T")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_suggest_assignee_workspace_khong_co_nhan_vien(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = await _mk_ceo(db_session, ws)
    await db_session.commit()

    result = await assignment_service.suggest_assignee(db_session, ceo, task_title="T")
    assert result["suggestions"] == []
```

**LƯU Ý cho người thực thi:** test `test_suggest_assignee_khop_dung_chuyen_mon` và `test_suggest_assignee_fallback_khi_khong_ai_khop_chuyen_mon` PHỤ THUỘC vào chất lượng thật của embedding client đang cấu hình cho test (`MockEmbeddingClient` hashing-trick nếu `embedding_mock=True`, xem docstring `embedding_service.py`). Nếu mock hashing không đủ phân biệt ngữ nghĩa 2 câu tiếng Việt khác chủ đề rõ ràng (design vs backend, hoặc ML vs kế toán/hành chính — các cặp từ này KHÔNG dùng chung từ nào nên hashing bag-of-words vẫn nên phân biệt được), 2 test này có thể fail dù logic đúng — nếu vậy, đọc kỹ `MockEmbeddingClient` trong `embedding_service.py` để xác nhận cách nó hoạt động và điều chỉnh câu test dùng từ trùng/khác rõ ràng hơn nếu cần, KHÔNG hạ ngưỡng `SEMANTIC_SEARCH_MIN_SCORE` để né vấn đề.

- [ ] **Step 2: Chạy test, xác nhận fail**

Run: `cd backend && python -m pytest tests/test_assignment_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.assignment_service'`.

- [ ] **Step 3: Viết `assignment_service.py`**

```python
# backend/app/services/assignment_service.py
"""Gợi ý người phù hợp khi giao task (2026-08-09) — spec
docs/superpowers/specs/2026-08-09-suggest-assignee-design.md.

Ưu tiên khớp chuyên môn (embedding_service.semantic_search trên
source_type="employee_expertise") trước; số task đang làm dở chỉ dùng để
tie-break khi nhiều người cùng hợp chuyên môn, hoặc làm fallback khi KHÔNG
ai khớp chuyên môn nào. KHÔNG tự động gán — chỉ trả gợi ý kèm lý do, CEO
vẫn xác nhận qua propose_actions như bình thường."""
from __future__ import annotations

import uuid

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, TaskAssignee, TaskStatus, User
from app.permissions import require_ceo
from app.services import embedding_service

_MAX_SUGGESTIONS = 2


async def _count_open_tasks_by_user(db: AsyncSession, workspace_id: uuid.UUID) -> dict[str, int]:
    rows = await db.execute(
        select(TaskAssignee.user_id, func.count(Task.id))
        .join(Task, TaskAssignee.task_id == Task.id)
        .where(Task.workspace_id == workspace_id, Task.status != TaskStatus.done)
        .group_by(TaskAssignee.user_id))
    return {str(uid): count for uid, count in rows.all()}


async def suggest_assignee(db: AsyncSession, actor: User, *, task_title: str,
                           task_description: str = "") -> dict:
    require_ceo(actor)
    query = f"{task_title}\n{task_description}".strip()
    open_counts = await _count_open_tasks_by_user(db, actor.workspace_id)

    matches: list[dict] = []
    if query:
        matches = await embedding_service.semantic_search(
            db, actor, query, source_types=["employee_expertise"], limit=10)

    if matches:
        matches.sort(key=lambda m: (-m["score"], open_counts.get(m["source_id"], 0)))
        top = matches[:_MAX_SUGGESTIONS]
        user_ids = [uuid.UUID(m["source_id"]) for m in top]
        rows = await db.execute(select(User).where(User.id.in_(user_ids)))
        name_by_id = {str(u.id): u.full_name for u in rows.scalars()}
        suggestions = []
        for m in top:
            uid = m["source_id"]
            name = name_by_id.get(uid, m.get("full_name", "?"))
            n_open = open_counts.get(uid, 0)
            suggestions.append({
                "user_id": uid, "full_name": name,
                "reason": f"{name} có chuyên môn khớp với task này "
                         f"(độ khớp {m['score']:.2f}), đang có {n_open} task dở."})
        return {"suggestions": suggestions}

    # Fallback: không ai khớp chuyên môn -> người rảnh nhất toàn workspace.
    rows = await db.execute(select(User).where(User.workspace_id == actor.workspace_id))
    all_users = list(rows.scalars())
    if not all_users:
        return {"suggestions": [], "note": "Chưa có nhân viên nào trong workspace."}
    freest = min(all_users, key=lambda u: open_counts.get(str(u.id), 0))
    n_open = open_counts.get(str(freest.id), 0)
    return {"suggestions": [{
        "user_id": str(freest.id), "full_name": freest.full_name,
        "reason": f"Không có ai khớp chuyên môn task này — {freest.full_name} "
                 f"đang rảnh nhất ({n_open} task dở)."}]}
```

- [ ] **Step 4: Chạy test, xác nhận PASS (điều chỉnh theo LƯU Ý ở Step 1 nếu mock embedding không đủ phân biệt)**

Run: `cd backend && python -m pytest tests/test_assignment_service.py -v`
Expected: PASS cả 5 test.

- [ ] **Step 5: Viết test thất bại cho tool `suggest_assignee`**

```python
# backend/tests/test_agent_tools_assignment.py
import pytest

from app.agent.tools import TOOLS, call_tool
from app.models import Role, User, Workspace


@pytest.mark.asyncio
async def test_suggest_assignee_tool_registered():
    assert "suggest_assignee" in TOOLS


@pytest.mark.asyncio
async def test_agent_tool_suggest_assignee_no_employees(db_session):
    ws = Workspace(name="A")
    db_session.add(ws)
    await db_session.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x", full_name="C",
              role=Role.ceo, is_root=True)
    db_session.add(ceo)
    await db_session.commit()

    result = await call_tool(db_session, ceo, "suggest_assignee",
                             {"task_title": "Thiet ke landing page"})
    assert result["suggestions"] == []
```

- [ ] **Step 6: Chạy test, xác nhận fail**

Run: `cd backend && python -m pytest tests/test_agent_tools_assignment.py -v`
Expected: FAIL — `KeyError: 'suggest_assignee'` (tool chưa đăng ký).

- [ ] **Step 7: Thêm tool `suggest_assignee`**

Trong `backend/app/agent/tools.py`, dòng 18-24 hiện có khối import theo alphabet:

```python
from app.services import (
    analytics_service, attachment_service, audit_service, auth_service, dashboard_service,
    directive_service, distiller_service, email_service, embedding_service, example_bank_service,
    instruction_service, note_service, notification_service, portal_service,
    report_schedule_service, report_service, resolver_service, search_service, skill_service,
    voice_service, work_service,
)
```

Thêm `assignment_service` vào đúng vị trí alphabet (giữa `analytics_service` và `attachment_service`):

```python
from app.services import (
    analytics_service, assignment_service, attachment_service, audit_service, auth_service,
    dashboard_service, directive_service, distiller_service, email_service, embedding_service,
    example_bank_service, instruction_service, note_service, notification_service,
    portal_service, report_schedule_service, report_service, resolver_service, search_service,
    skill_service, voice_service, work_service,
)
```

Rồi thêm gần `_register("assign_task", ...)`:

```python
class SuggestAssigneeToolIn(BaseModel):
    task_title: str
    task_description: str = ""


async def _suggest_assignee(db, actor, body: SuggestAssigneeToolIn) -> dict:
    return await assignment_service.suggest_assignee(
        db, actor, task_title=body.task_title, task_description=body.task_description)


_register("suggest_assignee",
          "Gợi ý người phù hợp nhất để giao 1 task (chỉ CEO, chỉ đọc — không "
          "gán gì). Dùng khi CEO yêu cầu tạo/giao task nhưng KHÔNG chỉ rõ tên "
          "người nhận -- gọi tool này TRƯỚC khi tạo task để biết nên đề xuất "
          "ai, rồi dùng kết quả điền vào create_task/assign_task qua "
          "propose_actions (đối tượng người nhận là SUY LUẬN nên phải qua "
          "luật mức 2). Xét theo chuyên môn nhân viên (field riêng, KHÁC HẲN "
          "Skill/tài liệu công ty) khớp ngữ nghĩa với nội dung task, và số "
          "task đang làm dở (ít hơn = rảnh hơn) khi nhiều người cùng hợp "
          "chuyên môn. Không tự động gán -- chỉ trả gợi ý kèm lý do để CEO "
          "xác nhận.",
          SuggestAssigneeToolIn, _suggest_assignee)
```

Thêm `"suggest_assignee"` vào `TOOL_GROUPS["work"]`:

```bash
grep -n '"work": frozenset' -A 6 backend/app/agent/tools.py
```

Đổi dòng đó thêm `"suggest_assignee"` vào set. KHÔNG thêm vào `SENSITIVE_TOOLS` (tool này không có `sensitive=True` trong `_register`, mặc định False — xác nhận chữ ký `_register` bằng `grep -n "def _register" -A 10 backend/app/agent/tools.py` nếu cần). KHÔNG thêm vào `SNAPSHOT_WRITE_TOOLS` (tool chỉ đọc, không ghi dữ liệu).

- [ ] **Step 8: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_agent_tools_assignment.py -v`
Expected: PASS cả 2 test.

- [ ] **Step 9: Cập nhật sentinel `len(TOOLS)` lần 2 (64 → 65)**

Với ĐỦ 11 file đã sửa ở Task 2 Step 8, đổi `len(TOOLS) == 64` thành `len(TOOLS) == 65`, nối thêm `+suggest_assignee` vào cuối comment.

- [ ] **Step 10: Thêm hướng dẫn vào system prompt**

Đọc `backend/app/agent/loop.py`, tìm đúng vị trí đã thêm câu về `$result[N].field` (đợt fix trước) để thêm câu mới ngay sau, cùng khối luật 3-mức:

```bash
grep -n "PHẢI dùng đúng cú pháp \$result\[N\]" backend/app/agent/loop.py
```

Thêm ngay sau đoạn đó (trước dòng `"3) Nhạy cảm..."`):

```python
        "Khi CEO yêu cầu tạo/giao task mà KHÔNG chỉ rõ người nhận (vd 'tạo "
        "task X' không nói giao ai, khác với 'giao task X cho Duy' đã rõ "
        "ràng): gọi suggest_assignee TRƯỚC để biết nên đề xuất ai, rồi dùng "
        "kết quả đó làm người nhận trong create_task/assign_task qua "
        "propose_actions (đối tượng người nhận là SUY LUẬN → luật mức 2), "
        "display_text nêu rõ lý do gợi ý (chuyên môn khớp hay đang rảnh) để "
        "CEO thấy trước khi duyệt.\n"
```

- [ ] **Step 11: Chạy full suite backend**

Run: `cd backend && python -m pytest tests/ -q`
Expected: PASS toàn bộ, không regression (kỳ vọng ~875 + 7 test mới của task này = ~882 passed).

- [ ] **Step 12: Export lại openapi.json (không đổi route HTTP nhưng theo convention luôn re-export sau khi động BE có schema mới)**

```bash
python scripts/export_openapi.py
```

- [ ] **Step 13: Commit**

```bash
git add backend/app/services/assignment_service.py backend/app/agent/tools.py backend/app/agent/loop.py backend/tests/test_assignment_service.py backend/tests/test_agent_tools_assignment.py backend/tests/test_delete_task_project.py backend/tests/test_agent_tools_semantic_search.py backend/tests/test_agent_tools_search.py backend/tests/test_agent_tools_resolver.py backend/tests/test_agent_tools_report_schedule.py backend/tests/test_agent_tools_report.py backend/tests/test_agent_tools_offboard.py backend/tests/test_agent_tools_directive.py backend/tests/test_agent_tools_change_role.py backend/tests/test_agent_tools_analytics.py backend/tests/test_agent_tools_propose_actions.py openapi.json
git commit -m "feat(agent): tool suggest_assignee goi y nguoi phu hop khi giao task theo chuyen mon + do ranh"
```

---

## Self-Review Notes

- **Spec coverage:** đối chiếu spec `2026-08-09-suggest-assignee-design.md` mục 1-6 — mục 1 (nhập chuyên môn) → Task 1; mục 2 (index) → Task 2; mục 3 (tool suggest_assignee, kết hợp 2 tiêu chí, fallback) → Task 3; mục "Nhập/sửa chuyên môn" (update_employee_expertise) → Task 2; mục "System prompt" → Task 3 Step 10. Test cần thêm (7 mục trong spec) đều có mặt: mục 1-2 → Task 2 test; mục 3-5 → Task 3 test; mục 6 → Task 3 test (`test_suggest_assignee_requires_ceo`); mục 7 (grep "skill" viết thường) — chưa có step riêng, bổ sung: chạy `grep -rn '"skill"' backend/app/services/assignment_service.py backend/app/agent/tools.py | grep -i suggest_assignee` để xác nhận sạch trước khi merge (thêm vào Task 3 Step 11 khi verify).
- **Placeholder scan:** không còn "TBD"/mô tả suông — 2 chỗ "LƯU Ý cho người thực thi" (Task 3 Step 1) giải thích rõ RỦI RO CỤ THỂ (mock embedding có thể không đủ phân biệt) và hướng xử lý, không phải placeholder che giấu thiếu sót.
- **Type consistency:** `assignment_service.suggest_assignee(db, actor, *, task_title, task_description="") -> dict` nhất quán giữa Task 3 Step 3 (định nghĩa) và Step 7 (tool gọi). `SuggestAssigneeToolIn` khớp đúng 2 field `task_title`/`task_description` dùng trong `_suggest_assignee`. `embedding_service.index_employee_expertise(db, workspace_id, user)` nhất quán giữa Task 2 (định nghĩa) và `auth_service.update_employee_expertise` (Task 2, gọi lại) và test Task 3 (`_mk_employee_with_expertise` helper gọi đúng chữ ký).
- **Rủi ro cần theo dõi lúc thực thi:** sentinel `len(TOOLS)` phải tăng ĐÚNG 2 lần (63→64 ở Task 2, 64→65 ở Task 3) qua ĐỦ 11 file — đây là lỗi dễ bỏ sót nhất theo bài học project, đã nhấn mạnh trong Global Constraints và từng Step liên quan.
