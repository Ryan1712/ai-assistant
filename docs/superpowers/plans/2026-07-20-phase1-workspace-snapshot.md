# Phase 1 — Workspace Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bức tranh workspace dạng text nén (SQL tính sẵn, cache Redis) tiêm vào system prompt theo phạm vi quyền của actor → câu hỏi tình hình thường nhật trả lời ngay lượt đầu, 0 tool call, số liệu đúng.

**Architecture:** `snapshot_service` build DATA per-workspace (JSON, SQL aggregates, KHÔNG gọi LLM) cache Redis TTL `snapshot_ttl_seconds`; RENDER text per-actor tại thời điểm request bằng chính `visible_project_ids/visible_task_ids/visible_user_ids` (quyền luôn tươi — data cache chung không lộ vượt quyền). System prompt tách 2 block [tĩnh có cache_control, động] để snapshot đổi không phá cache tools+static. Agent ghi qua tool → invalidate key ngay (AI thấy ngay việc mình vừa làm); ghi qua REST của FE → TTL 300s lo.

**Tech Stack:** FastAPI + SQLAlchemy async (như hiện tại), redis.asyncio, pattern Fake-store cho test (như FakeEventPublisher).

**Spec gốc:** `docs/superpowers/specs/2026-07-19-ai-intelligence-upgrade.md` §5 (+§3 config).

## Global Constraints

- Mọi query lọc workspace; **snapshot KHÔNG được lộ dữ liệu vượt quyền**: cắt theo `visible_project_ids/visible_task_ids/visible_user_ids` (app/permissions.py) tính TƯƠI mỗi request.
- Builder **không gọi LLM** — thuần SQL + template.
- Snapshot là tăng cường: **mọi lỗi (redis chết, SQL lỗi) → trả "" và log, TUYỆT ĐỐI không phá chat**.
- "Hôm nay"/deadline hiểu theo **giờ VN (UTC+7)** — dùng `app.tz.VN_TZ`, cùng lớp bug đã fix ở dashboard/voice/audit.
- Config: `snapshot_ttl_seconds: int = 300` (spec §3).
- Cache breakpoints ≤4: tools(1) + system-block-tĩnh(1) + message-cuối(1) = 3.
- TDD; mỗi task một commit; test chạy `./.venv/Scripts/python.exe -m pytest ...` trong `backend/`.
- KHÔNG dùng PowerShell Get-Content|Set-Content với file tiếng Việt — dùng tool Edit/Write.
- Đổi API contract → export openapi (Phase 1 KHÔNG đổi contract REST — không cần).
- **Deviation đã chốt so với spec §5.2** (spec cho phép "chọn cách rẻ hơn"): thay "worker nền + hook debounce arq" bằng **lazy build-on-miss + TTL + invalidate tại choke point agent** (`call_tool` write set + `resolve_confirmation`). Ghi vào BASELINE khi xong.
- Số liệu môi trường (BASELINE Phase 0): dev chạy glm-4.7-flash qua gateway beeknoee (1-concurrency, không passthrough cache); eval scenario `trung-ten-khong-tu-chon` đang FAIL chủ đích — KHÔNG sửa cho xanh ở phase này.

---

### Task 1: Config TTL + SnapshotStore (Fake/Redis) + fixture autouse

**Files:**
- Modify: `backend/app/config.py`
- Create: `backend/app/services/snapshot_service.py` (phần store)
- Modify: `backend/tests/conftest.py` (fixture autouse)
- Test: `backend/tests/test_snapshot_store.py`

**Interfaces:**
- Consumes: `get_settings()`.
- Produces: `Settings.snapshot_ttl_seconds: int = 300`; module `snapshot_service` với: `FakeSnapshotStore` (attrs `.data: dict`, `.deleted: list`), `RedisSnapshotStore(redis)`, `get_snapshot_store()` (@lru_cache); cả 3 method async `get(key) -> str|None`, `set(key, value, ttl)`, `delete(key)`. Conftest fixture autouse `fake_snapshot_store` patch `snapshot_service.get_snapshot_store` → mọi test dùng Fake (không cần redis). Task 4 dùng store; Task 6 dùng fixture để spy invalidation.

- [ ] **Step 1: Viết failing test**

Tạo `backend/tests/test_snapshot_store.py`:

```python
"""Phase 1 (spec AI upgrade §5.2): store cache snapshot + config TTL."""
from app.config import Settings
from app.services import snapshot_service
from app.services.snapshot_service import FakeSnapshotStore


def test_config_snapshot_ttl_mac_dinh():
    s = Settings(_env_file=None)
    assert s.snapshot_ttl_seconds == 300


async def test_fake_store_get_set_delete():
    store = FakeSnapshotStore()
    assert await store.get("snapshot:ws1") is None
    await store.set("snapshot:ws1", "{\"a\": 1}", ttl=300)
    assert await store.get("snapshot:ws1") == "{\"a\": 1}"
    await store.delete("snapshot:ws1")
    assert await store.get("snapshot:ws1") is None
    assert store.deleted == ["snapshot:ws1"]


async def test_conftest_patch_store_thanh_fake(fake_snapshot_store):
    # fixture autouse: mọi test lấy store qua get_snapshot_store đều nhận Fake
    assert snapshot_service.get_snapshot_store() is fake_snapshot_store
    assert isinstance(fake_snapshot_store, FakeSnapshotStore)
```

- [ ] **Step 2: Chạy test xác nhận fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_snapshot_store.py -v`
Expected: FAIL — chưa có module/field.

- [ ] **Step 3: Implement**

`backend/app/config.py` — thêm vào `Settings` (cạnh `portal_base_url`):

```python
    # Snapshot workspace (spec AI upgrade §5): TTL fallback khi không có invalidation
    # (ghi từ REST của FE); ghi qua agent tool được invalidate ngay.
    snapshot_ttl_seconds: int = 300
```

Tạo `backend/app/services/snapshot_service.py`:

```python
"""Workspace snapshot (spec AI upgrade §5) — bức tranh công ty dạng text nén.

Kiến trúc: build DATA per-workspace (SQL aggregates, KHÔNG LLM) cache Redis TTL;
render TEXT per-actor tại request bằng visible_* của app/permissions.py (quyền
luôn tươi — data cache chung, không lộ vượt quyền). Lỗi bất kỳ → trả "" (snapshot
là tăng cường, không bao giờ được phá chat).

Refresh (deviation §5.2 đã chốt): lazy build-on-miss + TTL + invalidate() gọi từ
agent loop sau write-tool — thay cho worker nền/debounce arq (spec cho phép chọn
cách rẻ hơn).
"""
from __future__ import annotations

import abc
import logging
import uuid
from functools import lru_cache

logger = logging.getLogger(__name__)


class SnapshotStore(abc.ABC):
    @abc.abstractmethod
    async def get(self, key: str) -> str | None: ...

    @abc.abstractmethod
    async def set(self, key: str, value: str, ttl: int) -> None: ...

    @abc.abstractmethod
    async def delete(self, key: str) -> None: ...


class FakeSnapshotStore(SnapshotStore):
    """Test double: dict trong RAM, không TTL thật; .deleted ghi lại invalidation."""

    def __init__(self):
        self.data: dict[str, str] = {}
        self.deleted: list[str] = []

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, ttl: int) -> None:
        self.data[key] = value

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)
        self.deleted.append(key)


class RedisSnapshotStore(SnapshotStore):
    def __init__(self, redis):
        self._redis = redis

    async def get(self, key: str) -> str | None:
        raw = await self._redis.get(key)
        if raw is None:
            return None
        return raw.decode() if isinstance(raw, bytes) else raw

    async def set(self, key: str, value: str, ttl: int) -> None:
        await self._redis.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)


@lru_cache
def get_snapshot_store() -> SnapshotStore:
    import redis.asyncio as redis_asyncio

    from app.config import get_settings

    # Timeout ngắn: redis chết thì get_snapshot_text bắt exception trả "" —
    # không được treo request chat vài chục giây chờ TCP.
    client = redis_asyncio.from_url(get_settings().redis_url,
                                    socket_connect_timeout=2, socket_timeout=2)
    return RedisSnapshotStore(client)


def _key(workspace_id: uuid.UUID | str) -> str:
    return f"snapshot:{workspace_id}"
```

`backend/tests/conftest.py` — thêm cuối file:

```python
@pytest.fixture(autouse=True)
def fake_snapshot_store(monkeypatch):
    # Mọi test dùng FakeSnapshotStore — unit test không cần redis thật, và
    # agent-loop test không ghi rác vào redis dev.
    from app.services import snapshot_service
    store = snapshot_service.FakeSnapshotStore()
    monkeypatch.setattr(snapshot_service, "get_snapshot_store", lambda: store)
    return store
```

- [ ] **Step 4: Chạy test xác nhận pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_snapshot_store.py tests/test_chat_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/app/services/snapshot_service.py backend/tests/conftest.py backend/tests/test_snapshot_store.py
git commit -m "feat(be): snapshot store (fake/redis) + config snapshot_ttl_seconds (Phase 1)"
```

---

### Task 2: Builder `build_workspace_data` — SQL aggregates per-workspace

**Files:**
- Modify: `backend/app/services/snapshot_service.py`
- Test: `backend/tests/test_snapshot_builder.py`

**Interfaces:**
- Consumes: models `Project, Task, TaskAssignee, TaskUpdate, User, TaskStatus`; `app.tz.VN_TZ`.
- Produces: `async build_workspace_data(db, workspace_id, *, now: datetime | None = None) -> dict` — MỌI id là str (JSON-safe). Shape (Task 3 render từ đây, đừng đổi tên key):

```python
{
  "built_at": "<iso utc>",
  "projects": [{"id", "name", "status", "deadline",      # deadline iso hoặc None
                 "task_total", "task_open", "task_blocked",
                 "task_overdue", "task_done", "percent_avg"}],
  "users": [{"id", "full_name", "role",                  # role = "ceo"|"manager"|"employee"
              "manager_name",                              # str hoặc None
              "open_count", "overdue_count",
              "last_update_at",                            # iso hoặc None (TaskUpdate mới nhất user đó viết)
              "doing": [{"task_id", "title", "project_name",
                          "percent", "deadline"}]}],        # in_progress, tối đa 3, sort deadline gần trước (None cuối)
  "due_today": [{"task_id", "title", "project_name", "assignees": ["tên", ...]}],
  "overdue":   [{"task_id", "title", "project_name", "assignees": [...], "deadline"}],
  "updates_24h": [{"task_id", "task_title", "author", "content", "percent", "at"}],  # mới nhất trước
}
```

Quy tắc số liệu: `task_open` = status != done; `task_overdue` = open + deadline < now (so theo NGÀY lịch VN, như dashboard `_dl_date`); `percent_avg` = round(mean(percent của MỌI task project)) hoặc 0 nếu không task; `due_today`/`overdue` chỉ task open toàn workspace; `updates_24h` = TaskUpdate 24h qua toàn workspace.

- [ ] **Step 1: Viết failing test**

Tạo `backend/tests/test_snapshot_builder.py`:

```python
"""Phase 1: builder SQL aggregates — thuần data, chưa render/chưa quyền."""
import uuid
from datetime import datetime, timedelta, timezone

from app.models import (
    Project, Role, Task, TaskAssignee, TaskStatus, TaskUpdate, User, Workspace,
)
from app.services.snapshot_service import build_workspace_data

NOW = datetime(2026, 7, 20, 3, 0, tzinfo=timezone.utc)  # 10:00 giờ VN 20/07


async def _world(db):
    ws = Workspace(name="A")
    db.add(ws)
    await db.flush()
    ceo = User(workspace_id=ws.id, email="c@a.vn", password_hash="x",
               full_name="Sếp", role=Role.ceo, is_root=True)
    db.add(ceo)
    await db.flush()
    ha = User(workspace_id=ws.id, email="ha@a.vn", password_hash="x",
              full_name="Hà Trần", role=Role.manager)
    db.add(ha)
    await db.flush()
    duy = User(workspace_id=ws.id, email="duy@a.vn", password_hash="x",
               full_name="Duy Phạm", role=Role.employee, manager_id=ha.id)
    db.add(duy)
    await db.flush()
    p = Project(workspace_id=ws.id, name="Marketing Q3", created_by=ceo.id)
    db.add(p)
    await db.flush()
    t1 = Task(workspace_id=ws.id, project_id=p.id, title="Landing page",
              status=TaskStatus.in_progress, percent=40,
              deadline=NOW + timedelta(days=3), created_by=ceo.id)
    t2 = Task(workspace_id=ws.id, project_id=p.id, title="Báo cáo thuế",
              status=TaskStatus.todo, percent=0,
              deadline=NOW - timedelta(days=2), created_by=ceo.id)   # quá hạn
    t3 = Task(workspace_id=ws.id, project_id=p.id, title="Việc xong",
              status=TaskStatus.done, percent=100, created_by=ceo.id)
    t4 = Task(workspace_id=ws.id, project_id=p.id, title="Họp khách",
              status=TaskStatus.todo, percent=0,
              deadline=NOW + timedelta(hours=2), created_by=ceo.id)  # đến hạn hôm nay (VN)
    db.add_all([t1, t2, t3, t4])
    await db.flush()
    db.add_all([
        TaskAssignee(workspace_id=ws.id, task_id=t1.id, user_id=duy.id),
        TaskAssignee(workspace_id=ws.id, task_id=t2.id, user_id=duy.id),
        TaskAssignee(workspace_id=ws.id, task_id=t4.id, user_id=ha.id),
    ])
    db.add(TaskUpdate(workspace_id=ws.id, task_id=t1.id, author_id=duy.id,
                      content="đã xong hero section", percent=40,
                      created_at=NOW - timedelta(hours=2)))
    await db.commit()
    return ws, ceo, ha, duy, p, (t1, t2, t3, t4)


async def test_project_aggregates(db_session):
    ws, *_ = await _world(db_session)
    data = await build_workspace_data(db_session, ws.id, now=NOW)
    (proj,) = data["projects"]
    assert proj["name"] == "Marketing Q3"
    assert proj["task_total"] == 4
    assert proj["task_open"] == 3
    assert proj["task_overdue"] == 1
    assert proj["task_done"] == 1
    assert proj["percent_avg"] == 35   # (40+0+100+0)/4
    assert isinstance(proj["id"], str)


async def test_user_workload_va_doing(db_session):
    ws, ceo, ha, duy, p, tasks = await _world(db_session)
    data = await build_workspace_data(db_session, ws.id, now=NOW)
    by_name = {u["full_name"]: u for u in data["users"]}
    assert by_name["Duy Phạm"]["open_count"] == 2
    assert by_name["Duy Phạm"]["overdue_count"] == 1
    assert by_name["Duy Phạm"]["manager_name"] == "Hà Trần"
    assert by_name["Duy Phạm"]["doing"][0]["title"] == "Landing page"
    assert by_name["Duy Phạm"]["doing"][0]["percent"] == 40
    assert by_name["Duy Phạm"]["last_update_at"] is not None
    assert by_name["Hà Trần"]["open_count"] == 1
    assert by_name["Sếp"]["open_count"] == 0


async def test_today_va_updates(db_session):
    ws, *_ = await _world(db_session)
    data = await build_workspace_data(db_session, ws.id, now=NOW)
    assert [t["title"] for t in data["due_today"]] == ["Họp khách"]
    assert data["due_today"][0]["assignees"] == ["Hà Trần"]
    assert [t["title"] for t in data["overdue"]] == ["Báo cáo thuế"]
    (upd,) = data["updates_24h"]
    assert upd["author"] == "Duy Phạm"
    assert upd["task_title"] == "Landing page"
    assert upd["percent"] == 40


async def test_workspace_khac_khong_lan(db_session):
    ws, *_ = await _world(db_session)
    ws2 = Workspace(name="B")
    db_session.add(ws2)
    await db_session.flush()
    u2 = User(workspace_id=ws2.id, email="x@b.vn", password_hash="x",
              full_name="Người B", role=Role.ceo)
    db_session.add(u2)
    await db_session.commit()
    data = await build_workspace_data(db_session, ws2.id, now=NOW)
    assert data["projects"] == []
    assert [u["full_name"] for u in data["users"]] == ["Người B"]
    assert data["due_today"] == [] and data["overdue"] == [] and data["updates_24h"] == []
```

- [ ] **Step 2: Chạy test xác nhận fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_snapshot_builder.py -v`
Expected: FAIL — `ImportError: build_workspace_data`.

- [ ] **Step 3: Implement builder**

Thêm vào `backend/app/services/snapshot_service.py` (sau phần store):

```python
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Task, TaskAssignee, TaskStatus, TaskUpdate, User
from app.tz import VN_TZ

_DOING_LIMIT = 3


def _vn_date(dt: datetime | None):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # SQLite test trả naive — giá trị luôn UTC
    return dt.astimezone(VN_TZ).date()


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


async def build_workspace_data(db: AsyncSession, workspace_id, *,
                               now: datetime | None = None) -> dict:
    """Aggregates SQL per-workspace, KHÔNG LLM, KHÔNG quyền (cắt quyền ở render).
    Mọi id là str để json round-trip qua Redis không đổi kiểu."""
    now = now or datetime.now(timezone.utc)
    today_vn = _vn_date(now)

    projects = (await db.execute(select(Project).where(
        Project.workspace_id == workspace_id).order_by(Project.created_at.asc())
    )).scalars().all()
    users = (await db.execute(select(User).where(
        User.workspace_id == workspace_id).order_by(User.full_name.asc())
    )).scalars().all()
    tasks = (await db.execute(select(Task).where(
        Task.workspace_id == workspace_id))).scalars().all()
    assignees = (await db.execute(select(TaskAssignee).where(
        TaskAssignee.workspace_id == workspace_id))).scalars().all()

    name_by_uid = {u.id: u.full_name for u in users}
    pname_by_id = {p.id: p.name for p in projects}
    task_by_id = {t.id: t for t in tasks}
    uids_by_task: dict = {}
    tids_by_user: dict = {}
    for a in assignees:
        uids_by_task.setdefault(a.task_id, []).append(a.user_id)
        tids_by_user.setdefault(a.user_id, []).append(a.task_id)

    def _is_open(t: Task) -> bool:
        return t.status != TaskStatus.done

    def _is_overdue(t: Task) -> bool:
        d = _vn_date(t.deadline)
        return _is_open(t) and d is not None and d < today_vn

    out_projects = []
    for p in projects:
        pt = [t for t in tasks if t.project_id == p.id]
        out_projects.append({
            "id": str(p.id), "name": p.name, "status": p.status,
            "deadline": _iso(p.deadline),
            "task_total": len(pt),
            "task_open": sum(1 for t in pt if _is_open(t)),
            "task_blocked": sum(1 for t in pt if t.status == TaskStatus.blocked),
            "task_overdue": sum(1 for t in pt if _is_overdue(t)),
            "task_done": sum(1 for t in pt if t.status == TaskStatus.done),
            "percent_avg": round(sum(t.percent for t in pt) / len(pt)) if pt else 0,
        })

    since = now - timedelta(hours=24)
    upd_rows = (await db.execute(
        select(TaskUpdate).where(TaskUpdate.workspace_id == workspace_id,
                                 TaskUpdate.created_at >= since)
        .order_by(TaskUpdate.created_at.desc()))).scalars().all()
    last_update_by_author: dict = {}
    all_upd_rows = (await db.execute(
        select(TaskUpdate.author_id, TaskUpdate.created_at).where(
            TaskUpdate.workspace_id == workspace_id))).all()
    for author_id, created_at in all_upd_rows:
        cur = last_update_by_author.get(author_id)
        if cur is None or created_at > cur:
            last_update_by_author[author_id] = created_at

    out_users = []
    for u in users:
        utasks = [task_by_id[tid] for tid in tids_by_user.get(u.id, [])
                  if tid in task_by_id]
        open_tasks = [t for t in utasks if _is_open(t)]
        doing = sorted((t for t in open_tasks if t.status == TaskStatus.in_progress),
                       key=lambda t: (t.deadline is None,
                                      t.deadline or datetime.max.replace(tzinfo=timezone.utc)))
        out_users.append({
            "id": str(u.id), "full_name": u.full_name, "role": u.role.value,
            "manager_name": name_by_uid.get(u.manager_id),
            "open_count": len(open_tasks),
            "overdue_count": sum(1 for t in open_tasks if _is_overdue(t)),
            "last_update_at": _iso(last_update_by_author.get(u.id)),
            "doing": [{"task_id": str(t.id), "title": t.title,
                       "project_name": pname_by_id.get(t.project_id, ""),
                       "percent": t.percent, "deadline": _iso(t.deadline)}
                      for t in doing[:_DOING_LIMIT]],
        })

    def _task_line(t: Task) -> dict:
        return {"task_id": str(t.id), "title": t.title,
                "project_name": pname_by_id.get(t.project_id, ""),
                "assignees": [name_by_uid.get(uid, "?")
                              for uid in uids_by_task.get(t.id, [])]}

    due_today = [t for t in tasks if _is_open(t) and _vn_date(t.deadline) == today_vn]
    overdue = [t for t in tasks if _is_overdue(t)]

    return {
        "built_at": now.isoformat(),
        "projects": out_projects,
        "users": out_users,
        "due_today": [_task_line(t) for t in due_today],
        "overdue": [{**_task_line(t), "deadline": _iso(t.deadline)} for t in overdue],
        "updates_24h": [{"task_id": str(r.task_id),
                         "task_title": task_by_id[r.task_id].title
                         if r.task_id in task_by_id else "?",
                         "author": name_by_uid.get(r.author_id, "?"),
                         "content": r.content, "percent": r.percent,
                         "at": _iso(r.created_at)} for r in upd_rows],
    }
```

- [ ] **Step 4: Chạy test xác nhận pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_snapshot_builder.py -v`
Expected: PASS 4/4.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/snapshot_service.py backend/tests/test_snapshot_builder.py
git commit -m "feat(be): snapshot builder SQL aggregates per-workspace (Phase 1)"
```

---

### Task 3: Renderer per-actor — cắt theo quyền + template text

**Files:**
- Modify: `backend/app/services/snapshot_service.py`
- Test: `backend/tests/test_snapshot_render.py`

**Interfaces:**
- Consumes: dict data của Task 2 (id đều str).
- Produces: `render_for_actor(data: dict, actor_user_id: str, *, visible_projects: set[str], visible_tasks: set[str], visible_users: set[str], now: datetime | None = None) -> str`. Text bắt đầu `# Trạng thái công ty`; sections `## Dự án`, `## Nhân sự & khối lượng`, `## Hôm nay`. Quy tắc cắt: project theo visible_projects; dòng user theo visible_users; `doing`/`due_today`/`overdue`/`updates_24h` lọc từng phần tử theo visible_tasks. Caps: 20 project, 30 user, 12 dòng mỗi list hôm nay, 10 update; toàn văn cắt 8000 ký tự kèm ghi chú. Data rỗng hoàn toàn (không project/task/update nhìn thấy và users chỉ còn chính mình) vẫn render header + "(chưa có dữ liệu)". Task 4 gọi hàm này.

- [ ] **Step 1: Viết failing test**

Tạo `backend/tests/test_snapshot_render.py`:

```python
"""Phase 1: render per-actor — QUAN TRỌNG NHẤT là test không lộ vượt quyền."""
from datetime import datetime, timezone

from app.services.snapshot_service import render_for_actor

NOW = datetime(2026, 7, 20, 3, 0, tzinfo=timezone.utc)

DATA = {
    "built_at": "2026-07-20T03:00:00+00:00",
    "projects": [
        {"id": "p1", "name": "Marketing Q3", "status": "active", "deadline": None,
         "task_total": 3, "task_open": 2, "task_blocked": 1, "task_overdue": 1,
         "task_done": 1, "percent_avg": 47},
        {"id": "p2", "name": "Dự án mật", "status": "active", "deadline": None,
         "task_total": 1, "task_open": 1, "task_blocked": 0, "task_overdue": 0,
         "task_done": 0, "percent_avg": 0},
    ],
    "users": [
        {"id": "u-ceo", "full_name": "Sếp", "role": "ceo", "manager_name": None,
         "open_count": 0, "overdue_count": 0, "last_update_at": None, "doing": []},
        {"id": "u-duy", "full_name": "Duy Phạm", "role": "employee",
         "manager_name": "Hà Trần", "open_count": 2, "overdue_count": 1,
         "last_update_at": "2026-07-20T01:00:00+00:00",
         "doing": [{"task_id": "t1", "title": "Landing page",
                    "project_name": "Marketing Q3", "percent": 40,
                    "deadline": "2026-07-23T03:00:00+00:00"}]},
        {"id": "u-nam", "full_name": "Nam Nguyễn", "role": "employee",
         "manager_name": "Hà Trần", "open_count": 1, "overdue_count": 0,
         "last_update_at": None,
         "doing": [{"task_id": "t9", "title": "Việc bí mật",
                    "project_name": "Dự án mật", "percent": 10, "deadline": None}]},
    ],
    "due_today": [{"task_id": "t4", "title": "Họp khách",
                   "project_name": "Marketing Q3", "assignees": ["Hà Trần"]}],
    "overdue": [{"task_id": "t2", "title": "Báo cáo thuế",
                 "project_name": "Marketing Q3", "assignees": ["Duy Phạm"],
                 "deadline": "2026-07-18T03:00:00+00:00"}],
    "updates_24h": [{"task_id": "t1", "task_title": "Landing page",
                     "author": "Duy Phạm", "content": "đã xong hero section",
                     "percent": 40, "at": "2026-07-20T01:00:00+00:00"}],
}


def test_ceo_thay_du_va_dung_format():
    text = render_for_actor(DATA, "u-ceo",
                            visible_projects={"p1", "p2"},
                            visible_tasks={"t1", "t2", "t4", "t9"},
                            visible_users={"u-ceo", "u-duy", "u-nam"}, now=NOW)
    assert text.startswith("# Trạng thái công ty")
    assert "## Dự án" in text and "## Nhân sự & khối lượng" in text and "## Hôm nay" in text
    assert "Marketing Q3" in text and "Dự án mật" in text
    assert "Duy Phạm" in text and "Landing page" in text and "40%" in text
    assert "Họp khách" in text and "Báo cáo thuế" in text
    assert "đã xong hero section" in text


def test_employee_khong_lo_du_lieu_nguoi_khac():
    # Duy chỉ thấy: project p1, task t1/t2 (của mình), user chính mình
    text = render_for_actor(DATA, "u-duy",
                            visible_projects={"p1"}, visible_tasks={"t1", "t2"},
                            visible_users={"u-duy"}, now=NOW)
    assert "Dự án mật" not in text
    assert "Việc bí mật" not in text
    assert "Nam Nguyễn" not in text
    assert "Họp khách" not in text          # t4 không thuộc visible_tasks
    assert "Landing page" in text            # việc của mình vẫn thấy
    assert "Báo cáo thuế" in text            # quá hạn của mình vẫn thấy


def test_manager_thay_nhanh_minh():
    # Hà (giả sử) thấy p1, t1/t2/t4, và user Duy (report) + chính mình (không có
    # trong DATA users thì bỏ qua im lặng — data build trước khi Hà join chẳng hạn)
    text = render_for_actor(DATA, "u-ha",
                            visible_projects={"p1"}, visible_tasks={"t1", "t2", "t4"},
                            visible_users={"u-ha", "u-duy"}, now=NOW)
    assert "Duy Phạm" in text and "Nam Nguyễn" not in text
    assert "Họp khách" in text and "Việc bí mật" not in text


def test_du_lieu_rong_van_co_header():
    empty = {"built_at": DATA["built_at"], "projects": [], "users": [],
             "due_today": [], "overdue": [], "updates_24h": []}
    text = render_for_actor(empty, "u-x", visible_projects=set(),
                            visible_tasks=set(), visible_users=set(), now=NOW)
    assert text.startswith("# Trạng thái công ty")
    assert "chưa có dữ liệu" in text


def test_cap_do_dai():
    big = dict(DATA)
    big["updates_24h"] = [{"task_id": "t1", "task_title": "Landing page",
                           "author": "Duy Phạm", "content": "x" * 500,
                           "percent": 1, "at": DATA["built_at"]}] * 50
    text = render_for_actor(big, "u-ceo", visible_projects={"p1", "p2"},
                            visible_tasks={"t1", "t2", "t4", "t9"},
                            visible_users={"u-ceo", "u-duy", "u-nam"}, now=NOW)
    assert len(text) <= 8100   # 8000 + ghi chú cắt
```

- [ ] **Step 2: Chạy test xác nhận fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_snapshot_render.py -v`
Expected: FAIL — chưa có `render_for_actor`.

- [ ] **Step 3: Implement renderer**

Thêm vào `backend/app/services/snapshot_service.py`:

```python
_ROLE_VN = {"ceo": "CEO", "manager": "Quản lý", "employee": "Nhân viên"}
_MAX_PROJECTS = 20
_MAX_USERS = 30
_MAX_TODAY = 12
_MAX_UPDATES = 10
_MAX_CHARS = 8000


def _fmt_dm(iso: str | None) -> str:
    """'2026-07-23T03:00:00+00:00' -> '23/07' theo giờ VN; None -> ''."""
    if not iso:
        return ""
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(VN_TZ).strftime("%d/%m")


def _fmt_hm(iso: str | None) -> str:
    if not iso:
        return ""
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(VN_TZ).strftime("%d/%m %H:%M")


def render_for_actor(data: dict, actor_user_id: str, *, visible_projects: set[str],
                     visible_tasks: set[str], visible_users: set[str],
                     now: datetime | None = None) -> str:
    """Cắt data theo phạm vi quyền rồi render text. Chỉ nhận id dạng str.

    An toàn mặc định: phần tử nào không nằm trong visible_* thì BỎ, kể cả khi
    điều đó làm section trống — thà thiếu còn hơn lộ vượt quyền."""
    now = now or datetime.now(timezone.utc)
    lines: list[str] = [
        f"# Trạng thái công ty (số liệu SQL lúc {_fmt_hm(data.get('built_at'))} giờ VN "
        "— tin cậy, ưu tiên trả lời từ đây thay vì gọi tool tra lại)"
    ]

    projects = [p for p in data.get("projects", []) if p["id"] in visible_projects]
    users = [u for u in data.get("users", []) if u["id"] in visible_users]
    due_today = [t for t in data.get("due_today", []) if t["task_id"] in visible_tasks]
    overdue = [t for t in data.get("overdue", []) if t["task_id"] in visible_tasks]
    updates = [u for u in data.get("updates_24h", []) if u["task_id"] in visible_tasks]

    if not projects and not users and not due_today and not overdue and not updates:
        lines.append("(chưa có dữ liệu trong phạm vi của bạn)")
        return "\n".join(lines)

    if projects:
        lines.append("## Dự án")
        for p in projects[:_MAX_PROJECTS]:
            dl = f", deadline {_fmt_dm(p['deadline'])}" if p["deadline"] else ""
            lines.append(
                f"- {p['name']} — {p['status']}, tiến độ TB {p['percent_avg']}%, "
                f"{p['task_total']} task ({p['task_open']} mở, {p['task_blocked']} blocked, "
                f"{p['task_overdue']} trễ hạn, {p['task_done']} xong){dl}")

    if users:
        lines.append("## Nhân sự & khối lượng")
        for u in users[:_MAX_USERS]:
            mgr = f", quản lý: {u['manager_name']}" if u["manager_name"] else ""
            doing = [d for d in u.get("doing", []) if d["task_id"] in visible_tasks]
            doing_txt = "; đang làm: " + " | ".join(
                f"\"{d['title']}\" ({d['project_name']}, {d['percent']}%"
                + (f", hạn {_fmt_dm(d['deadline'])}" if d["deadline"] else "") + ")"
                for d in doing) if doing else ""
            upd = (f"; cập nhật gần nhất {_fmt_hm(u['last_update_at'])}"
                   if u["last_update_at"] else "")
            od = f", {u['overdue_count']} trễ hạn" if u["overdue_count"] else ""
            lines.append(f"- {u['full_name']} ({_ROLE_VN.get(u['role'], u['role'])}{mgr}) "
                         f"— {u['open_count']} task mở{od}{doing_txt}{upd}")

    lines.append(f"## Hôm nay ({(now.astimezone(VN_TZ)).strftime('%d/%m')})")
    if due_today:
        for t in due_today[:_MAX_TODAY]:
            who = ", ".join(t["assignees"]) or "chưa gán"
            lines.append(f"- Đến hạn hôm nay: \"{t['title']}\" ({t['project_name']} — {who})")
    if overdue:
        for t in overdue[:_MAX_TODAY]:
            who = ", ".join(t["assignees"]) or "chưa gán"
            lines.append(f"- QUÁ HẠN từ {_fmt_dm(t['deadline'])}: \"{t['title']}\" "
                         f"({t['project_name']} — {who})")
    if updates:
        for u in updates[:_MAX_UPDATES]:
            pct = f", {u['percent']}%" if u["percent"] is not None else ""
            content = (u["content"] or "")[:80]
            lines.append(f"- Cập nhật 24h: {u['author']}: \"{content}\" "
                         f"({u['task_title']}{pct}) lúc {_fmt_hm(u['at'])}")
    if not due_today and not overdue and not updates:
        lines.append("- (không có deadline/cập nhật đáng chú ý)")

    text = "\n".join(lines)
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + "\n(… snapshot dài quá đã bị cắt)"
    return text
```

- [ ] **Step 4: Chạy test xác nhận pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_snapshot_render.py -v`
Expected: PASS 5/5.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/snapshot_service.py backend/tests/test_snapshot_render.py
git commit -m "feat(be): snapshot renderer per-actor cat theo quyen (Phase 1)"
```

---

### Task 4: Orchestrator `get_snapshot_text` + cache + `invalidate` + resilience

**Files:**
- Modify: `backend/app/services/snapshot_service.py`
- Test: `backend/tests/test_snapshot_service.py`

**Interfaces:**
- Consumes: store (Task 1), builder (Task 2), renderer (Task 3), `visible_project_ids/visible_task_ids/visible_user_ids` (app/permissions.py — nhận `db, actor: User`).
- Produces: `async get_snapshot_text(db, actor: User, *, now=None) -> str` (cache-hit đọc JSON từ store; miss → build + `store.set` với TTL settings; luôn render tươi theo quyền actor; MỌI exception → `""` + log); `async invalidate(workspace_id) -> None` (delete key, nuốt lỗi). Task 6 gọi cả hai từ loop.

- [ ] **Step 1: Viết failing test**

Tạo `backend/tests/test_snapshot_service.py`:

```python
"""Phase 1: orchestrator — cache hit/miss, cắt quyền end-to-end, không bao giờ raise."""
import json

from app.services import snapshot_service
from app.services.snapshot_service import get_snapshot_text, invalidate

from tests.test_snapshot_builder import NOW, _world


async def test_miss_build_set_cache_roi_hit(db_session, fake_snapshot_store):
    ws, ceo, ha, duy, p, tasks = await _world(db_session)
    text = await get_snapshot_text(db_session, ceo, now=NOW)
    assert "Marketing Q3" in text and "Duy Phạm" in text
    key = f"snapshot:{ws.id}"
    assert key in fake_snapshot_store.data          # đã SET sau miss
    # sửa cache bằng tay → lần 2 đọc từ cache (không build lại)
    cached = json.loads(fake_snapshot_store.data[key])
    cached["projects"][0]["name"] = "TÊN TỪ CACHE"
    fake_snapshot_store.data[key] = json.dumps(cached, ensure_ascii=False)
    text2 = await get_snapshot_text(db_session, ceo, now=NOW)
    assert "TÊN TỪ CACHE" in text2


async def test_employee_bi_cat_theo_quyen_end_to_end(db_session, fake_snapshot_store):
    ws, ceo, ha, duy, p, (t1, t2, t3, t4) = await _world(db_session)
    text = await get_snapshot_text(db_session, duy, now=NOW)
    assert "Landing page" in text                    # task mình
    assert "Duy Phạm" in text
    assert "Sếp" not in text.split("## Nhân sự")[1].split("## Hôm nay")[0] \
        if "## Nhân sự" in text else True             # dòng workload người khác không có
    assert "Họp khách" not in text                   # task của Hà, Duy không thấy


async def test_invalidate_xoa_key(db_session, fake_snapshot_store):
    ws, ceo, *_ = await _world(db_session)
    await get_snapshot_text(db_session, ceo, now=NOW)
    key = f"snapshot:{ws.id}"
    assert key in fake_snapshot_store.data
    await invalidate(ws.id)
    assert key not in fake_snapshot_store.data
    assert fake_snapshot_store.deleted == [key]


async def test_store_no_khong_pha_chat(db_session, monkeypatch):
    ws, ceo, *_ = await _world(db_session)

    class _Boom:
        async def get(self, key):
            raise RuntimeError("redis chết")

        async def set(self, key, value, ttl):
            raise RuntimeError("redis chết")

        async def delete(self, key):
            raise RuntimeError("redis chết")

    monkeypatch.setattr(snapshot_service, "get_snapshot_store", lambda: _Boom())
    assert await get_snapshot_text(db_session, ceo, now=NOW) == ""   # không raise
    await invalidate(ws.id)                                          # không raise
```

- [ ] **Step 2: Chạy test xác nhận fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_snapshot_service.py -v`
Expected: FAIL — chưa có `get_snapshot_text`/`invalidate`.

- [ ] **Step 3: Implement**

Thêm vào `backend/app/services/snapshot_service.py`:

```python
from app.permissions import visible_project_ids, visible_task_ids, visible_user_ids


async def get_snapshot_text(db, actor, *, now: datetime | None = None) -> str:
    """Text '# Trạng thái công ty' theo phạm vi quyền actor.

    KHÔNG BAO GIỜ raise — snapshot là tăng cường; redis/SQL lỗi thì trả "" và
    log, chat vẫn chạy như trước Phase 1."""
    try:
        from app.config import get_settings

        store = get_snapshot_store()
        key = _key(actor.workspace_id)
        raw = await store.get(key)
        if raw is None:
            data = await build_workspace_data(db, actor.workspace_id, now=now)
            await store.set(key, json.dumps(data, ensure_ascii=False),
                            get_settings().snapshot_ttl_seconds)
        else:
            data = json.loads(raw)
        vp = {str(i) for i in await visible_project_ids(db, actor)}
        vt = {str(i) for i in await visible_task_ids(db, actor)}
        vu = {str(i) for i in await visible_user_ids(db, actor)}
        return render_for_actor(data, str(actor.id), visible_projects=vp,
                                visible_tasks=vt, visible_users=vu, now=now)
    except Exception:
        logger.exception("snapshot fail cho workspace %s", actor.workspace_id)
        return ""


async def invalidate(workspace_id) -> None:
    """Xóa cache snapshot của workspace (gọi sau write-tool của agent). Nuốt lỗi."""
    try:
        await get_snapshot_store().delete(_key(workspace_id))
    except Exception:
        logger.exception("snapshot invalidate fail cho workspace %s", workspace_id)
```

- [ ] **Step 4: Chạy test xác nhận pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_snapshot_service.py tests/test_snapshot_builder.py tests/test_snapshot_render.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/snapshot_service.py backend/tests/test_snapshot_service.py
git commit -m "feat(be): get_snapshot_text cache+quyen+resilience, invalidate (Phase 1)"
```

---

### Task 5: llm_client — system 2 block [tĩnh cache, động]

**Files:**
- Modify: `backend/app/agent/llm_client.py`
- Test: `backend/tests/test_llm_client_cache.py` (thêm test)

**Interfaces:**
- Consumes: `AnthropicLLMClient.stream(system=...)` hiện nhận str.
- Produces: `stream(system: str | list[dict], ...)` — str giữ nguyên hành vi cũ (1 block + cache_control); list block text `{"type": "text", "text": ...}` → cache_control đặt vào **block ĐẦU** (phần tĩnh), các block sau giữ nguyên, KHÔNG mutate input. `LLMClient`/`FakeLLMClient` không cần đổi (nhận gì ghi nấy vào `.calls`). Task 6 truyền `[static, dynamic]`.

- [ ] **Step 1: Viết failing test**

Thêm vào cuối `backend/tests/test_llm_client_cache.py`:

```python
async def test_system_2_block_cache_o_block_dau():
    """Phase 1: [tĩnh, động] — breakpoint ở block tĩnh; block động (snapshot đổi
    thường xuyên) không phá cache của tools+phần tĩnh."""
    fake = _FakeClient()
    llm = AnthropicLLMClient(fake, model="m")
    sys_blocks = [{"type": "text", "text": "phần tĩnh"},
                  {"type": "text", "text": "# Trạng thái công ty\n..."}]
    async for _ in llm.stream(system=sys_blocks, messages=[], tools=[]):
        pass
    sent = fake.messages.kwargs["system"]
    assert sent[0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in sent[1]
    assert sent[1]["text"].startswith("# Trạng thái công ty")
    # không mutate input
    assert "cache_control" not in sys_blocks[0]


async def test_system_str_giu_hanh_vi_cu():
    fake = _FakeClient()
    llm = AnthropicLLMClient(fake, model="m")
    async for _ in llm.stream(system="sys", messages=[], tools=[]):
        pass
    assert fake.messages.kwargs["system"] == [
        {"type": "text", "text": "sys", "cache_control": {"type": "ephemeral"}}]
```

- [ ] **Step 2: Chạy test xác nhận fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_llm_client_cache.py -v`
Expected: 1 test mới FAIL (list chưa hỗ trợ).

- [ ] **Step 3: Implement**

Trong `AnthropicLLMClient.stream`, thay đoạn dựng `system_payload` hiện tại:

```python
        if isinstance(system, str):
            system_payload = [{"type": "text", "text": system,
                               "cache_control": {"type": "ephemeral"}}]
        else:
            # [tĩnh, *động] (Phase 1): breakpoint ở block ĐẦU — block động
            # (instruction/snapshot đổi thường xuyên) đứng sau, không phá cache
            # của tools + phần tĩnh. Copy dict, không mutate input.
            system_payload = [{**system[0], "cache_control": {"type": "ephemeral"}},
                              *(dict(b) for b in system[1:])]
```

Cập nhật chữ ký ở cả `LLMClient.stream` abstract, `FakeLLMClient.stream`, `AnthropicLLMClient.stream`: `system: str | list[dict]`.

- [ ] **Step 4: Chạy test xác nhận pass**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_llm_client_cache.py tests/test_agent_llm_client.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/llm_client.py backend/tests/test_llm_client_cache.py
git commit -m "feat(be): system prompt 2 block tinh/dong, cache o block tinh (Phase 1)"
```

---

### Task 6: Tích hợp loop — tiêm snapshot, luật grounding, invalidate sau write-tool

**Files:**
- Modify: `backend/app/agent/loop.py`
- Modify: `backend/app/agent/tools.py` (thêm `SNAPSHOT_WRITE_TOOLS`)
- Test: `backend/tests/test_agent_loop_snapshot.py`

**Interfaces:**
- Consumes: `snapshot_service.get_snapshot_text/invalidate` (Task 4), llm_client 2-block (Task 5), fixture `fake_snapshot_store` (Task 1).
- Produces:
  - `tools.py`: `SNAPSHOT_WRITE_TOOLS: frozenset[str]` = {"create_project", "update_project", "delete_project", "create_task", "update_task", "delete_task", "assign_task", "unassign_task", "add_task_update", "offboard_user", "change_user_role"}.
  - `loop.py`: mỗi vòng build `system_payload` = str (khi không có phần động) hoặc `[{"type":"text","text": static}, {"type":"text","text": dynamic}]`; dynamic = instructions block (nếu có) + snapshot text (nếu có) nối bằng `"\n\n"`. Sau khi chạy xong batch tool trong 1 vòng: nếu có tool thuộc `SNAPSHOT_WRITE_TOOLS` → `await snapshot_service.invalidate(req.workspace_id)`. `resolve_confirmation` nhánh approved với tool thuộc set → invalidate.
  - `_build_system_prompt` thêm 1 câu luật grounding (xem Step 3).

- [ ] **Step 1: Viết failing test**

Tạo `backend/tests/test_agent_loop_snapshot.py`:

```python
"""Phase 1: loop tiêm snapshot vào system (block động) + invalidate sau write-tool."""
import pytest

from app.agent.llm_client import FakeLLMClient, StreamDone, TextDelta, ToolUseBlock
from app.agent.loop import resolve_confirmation, run_agent_loop
from app.agent.publisher import FakeEventPublisher
from app.models import ChatRequest, ChatRequestStatus, Message, MessageRole

from tests.test_snapshot_builder import NOW, _world


async def _request(db, ws, ceo, conv=None):
    from app.models import Conversation
    if conv is None:
        conv = Conversation(workspace_id=ws.id, user_id=ceo.id)
        db.add(conv)
        await db.flush()
    req = ChatRequest(workspace_id=ws.id, conversation_id=conv.id, user_id=ceo.id,
                      content="hoi tinh hinh", queue_position=1.0)
    db.add(req)
    db.add(Message(workspace_id=ws.id, conversation_id=conv.id, chat_request_id=req.id,
                   role=MessageRole.user,
                   content=[{"type": "text", "text": req.content}]))
    await db.commit()
    return req


def _system_of(llm: FakeLLMClient, call_idx: int = 0):
    return llm.calls[call_idx]["system"]


@pytest.mark.asyncio
async def test_snapshot_nam_trong_block_dong(db_session):
    ws, ceo, ha, duy, p, tasks = await _world(db_session)
    req = await _request(db_session, ws, ceo)
    llm = FakeLLMClient(turns=[[
        TextDelta(text="ok"),
        StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1),
    ]])
    await run_agent_loop(db_session, req, llm, FakeEventPublisher())

    system = _system_of(llm)
    assert isinstance(system, list) and len(system) == 2
    assert "Trạng thái công ty" not in system[0]["text"]   # tĩnh không chứa snapshot
    assert "# Trạng thái công ty" in system[1]["text"]
    assert "Marketing Q3" in system[1]["text"]
    # luật grounding nằm ở block tĩnh
    assert "Trạng thái công ty" in system[0]["text"] or "ưu tiên" in system[0]["text"]


@pytest.mark.asyncio
async def test_write_tool_invalidate_snapshot(db_session, fake_snapshot_store):
    ws, ceo, ha, duy, p, tasks = await _world(db_session)
    req = await _request(db_session, ws, ceo)
    llm = FakeLLMClient(turns=[
        [StreamDone(tool_uses=[ToolUseBlock(id="t1", name="create_task",
                                            input={"project_id": str(p.id),
                                                   "title": "Task mới"})],
                    stop_reason="tool_use", input_tokens=1, output_tokens=1)],
        [TextDelta(text="đã tạo"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
    ])
    await run_agent_loop(db_session, req, llm, FakeEventPublisher())
    assert f"snapshot:{ws.id}" in fake_snapshot_store.deleted


@pytest.mark.asyncio
async def test_read_tool_khong_invalidate(db_session, fake_snapshot_store):
    ws, ceo, *_ = await _world(db_session)
    req = await _request(db_session, ws, ceo)
    llm = FakeLLMClient(turns=[
        [StreamDone(tool_uses=[ToolUseBlock(id="t1", name="list_projects", input={})],
                    stop_reason="tool_use", input_tokens=1, output_tokens=1)],
        [TextDelta(text="xong"),
         StreamDone(tool_uses=[], stop_reason="end_turn", input_tokens=1, output_tokens=1)],
    ])
    await run_agent_loop(db_session, req, llm, FakeEventPublisher())
    assert fake_snapshot_store.deleted == []


@pytest.mark.asyncio
async def test_confirm_approved_write_tool_invalidate(db_session, fake_snapshot_store):
    ws, ceo, ha, duy, p, (t1, *_rest) = await _world(db_session)
    req = await _request(db_session, ws, ceo)
    req.status = ChatRequestStatus.awaiting_confirmation
    req.pending_action = {"tool_name": "delete_task",
                          "tool_input": {"task_id": str(t1.id)}, "tool_use_id": "tu1"}
    await db_session.commit()

    await resolve_confirmation(db_session, req, approved=True)
    assert f"snapshot:{ws.id}" in fake_snapshot_store.deleted
```

- [ ] **Step 2: Chạy test xác nhận fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_agent_loop_snapshot.py -v`
Expected: FAIL (system vẫn là str; không invalidate).

- [ ] **Step 3: Implement**

`backend/app/agent/tools.py` — cuối file, cạnh `SENSITIVE_TOOLS`:

```python
# Tool làm THAY ĐỔI dữ liệu nuôi snapshot (project/task/người) — agent loop
# invalidate cache snapshot ngay sau khi chạy để lượt sau AI thấy việc mình vừa
# làm. Ghi từ REST của FE dựa vào TTL (spec §5.2, deviation đã chốt trong plan).
SNAPSHOT_WRITE_TOOLS: frozenset[str] = frozenset({
    "create_project", "update_project", "delete_project",
    "create_task", "update_task", "delete_task",
    "assign_task", "unassign_task", "add_task_update",
    "offboard_user", "change_user_role",
})
```

`backend/app/agent/loop.py`:

1. Import: dòng import tools thêm `SNAPSHOT_WRITE_TOOLS`; dòng import services thêm `snapshot_service`:

```python
from app.agent.tools import SENSITIVE_TOOLS, SNAPSHOT_WRITE_TOOLS, TOOLS, call_tool
from app.services import instruction_service, snapshot_service
```

2. `_build_system_prompt` — thêm câu luật grounding vào CUỐI chuỗi return (nối thêm 1 phần tử trước dấu đóng ngoặc):

```python
        "Nếu có mục '# Trạng thái công ty' trong system prompt: đó là số liệu SQL "
        "mới nhất theo đúng phạm vi quyền của người dùng — ưu tiên trả lời trực tiếp "
        "từ đó (0 lần gọi tool); chỉ gọi tool khi cần chi tiết không có sẵn ở đó."
```

3. Trong `run_agent_loop`, thay đoạn build system hiện tại (từ `system_prompt = _build_system_prompt(actor)` đến hết `if instructions_text:` block) bằng:

```python
            system_static = _build_system_prompt(actor)
            dynamic_parts: list[str] = []
            # Instruction + snapshot đọc DB/cache mỗi lượt → cập nhật là nạp lại ngay
            instructions_text = await instruction_service.active_instructions_text(
                db, req.workspace_id)
            if instructions_text:
                dynamic_parts.append("# Chỉ dẫn từ CEO công ty\n" + instructions_text)
            snapshot_text = await snapshot_service.get_snapshot_text(db, actor)
            if snapshot_text:
                dynamic_parts.append(snapshot_text)
            system_payload: str | list[dict] = system_static
            if dynamic_parts:
                # 2 block: [tĩnh (cache_control ở llm_client), động] — snapshot đổi
                # không phá cache tools + phần tĩnh.
                system_payload = [{"type": "text", "text": system_static},
                                  {"type": "text", "text": "\n\n".join(dynamic_parts)}]
```

và đổi `llm.stream(system=system_prompt, ...)` thành `llm.stream(system=system_payload, ...)`.

4. Sau vòng `for tu in done.tool_uses:` (sau `await db.commit()` của tool_results), thêm:

```python
            if any(tu.name in SNAPSHOT_WRITE_TOOLS for tu in done.tool_uses):
                # AI vừa đổi dữ liệu → lượt sau phải thấy ngay (không chờ TTL)
                await snapshot_service.invalidate(req.workspace_id)
```

5. Trong `resolve_confirmation`, sau `result = await call_tool(...)` nhánh approved:

```python
        if action["tool_name"] in SNAPSHOT_WRITE_TOOLS:
            from app.services import snapshot_service
            await snapshot_service.invalidate(req.workspace_id)
```

(import module-level đã có ở bước 1 — dùng thẳng, bỏ dòng import cục bộ nếu trùng.)

- [ ] **Step 4: Chạy test xác nhận pass + regression loop**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_agent_loop_snapshot.py tests/test_agent_loop_basic.py tests/test_agent_loop_confirmation.py tests/test_agent_loop_cancel_error.py tests/test_agent_trace_loop.py tests/test_system_prompt.py tests/test_worker.py -v`
Expected: PASS toàn bộ.

- [ ] **Step 5: Full suite**

Run: `./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS (trừ 3 dashboard flaky nếu đang trong khung giờ lỗi — đã biết).

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/loop.py backend/app/agent/tools.py backend/tests/test_agent_loop_snapshot.py
git commit -m "feat(be): tiem snapshot vao system prompt + invalidate sau write-tool (Phase 1)"
```

---

### Task 7: Eval — grader `expected_no_tools` + scenario Phase 1 + nới scenario cũ

**Files:**
- Modify: `backend/evals/grader.py`
- Modify: `backend/tests/test_eval_grader.py`
- Modify: `backend/evals/scenarios/core.yaml`
- Modify: `backend/evals/run_evals.py` (default `--phase` → 1)
- Modify: `backend/evals/README.md` (ghi key mới)

**Interfaces:**
- Consumes: grader hiện có.
- Produces: scenario key mới `expected_no_tools: true` → fail nếu `called_tools` khác rỗng (liệt kê tool đã gọi). 3 scenario mới `phase: 1`; 2 scenario cũ nới lỏng. Task 8 chạy với default phase mới.

- [ ] **Step 1: Viết failing test grader**

Thêm vào `backend/tests/test_eval_grader.py`:

```python
def test_expected_no_tools():
    s = {"expected_no_tools": True, "expected_status": "done"}
    assert grade(s, [], "done")["passed"] is True
    bad = grade(s, ["list_tasks"], "done")
    assert bad["passed"] is False
    assert "list_tasks" in bad["failures"][0]
```

- [ ] **Step 2: Chạy xác nhận fail**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_eval_grader.py -v`
Expected: test mới FAIL.

- [ ] **Step 3: Implement grader + scenarios**

`backend/evals/grader.py` — trong `grade()`, sau vòng expected_tools thêm:

```python
    if scenario.get("expected_no_tools") and called_tools:
        failures.append("kỳ vọng 0 tool nhưng đã gọi: " + ", ".join(called_tools))
```

(docstring thêm 1 dòng mô tả key.)

`backend/evals/scenarios/core.yaml`:

1. Sửa scenario `tra-cuu-tien-do-project`: XÓA dòng `expected_tools: [list_tasks]`, thêm `notes: "Phase 1: snapshot có thể trả lời 0-tool — không ép tool nữa, chỉ cần done + đúng."`.
2. Sửa scenario `dashboard-hom-nay`: XÓA `expected_tools: [get_today_dashboard]`, notes tương tự.
3. Thêm cuối file:

```yaml
- id: snapshot-tinh-hinh-du-an
  actor: ceo
  user_text: "Dự án Marketing Q3 đang thế nào?"
  expected_no_tools: true
  expected_status: done
  phase: 1
  notes: "Acceptance Phase 1: trả lời từ snapshot, 0 tool call (verify bằng trace)."

- id: snapshot-ai-dang-lam-gi
  actor: ceo
  user_text: "Duy đang làm gì?"
  expected_no_tools: true
  expected_status: done
  phase: 1

- id: snapshot-hom-nay-co-gi
  actor: ceo
  user_text: "Hôm nay có việc gì đến hạn hay quá hạn không?"
  expected_no_tools: true
  expected_status: done
  phase: 1
```

`backend/evals/run_evals.py`: đổi `ap.add_argument("--phase", type=int, default=0, ...)` thành `default=1` + sửa help: `"chạy scenario có phase <= giá trị này (default 1 = phase hiện tại của code)"`.

`backend/evals/README.md`: mục format scenario thêm dòng `expected_no_tools: true   # fail nếu gọi bất kỳ tool nào (acceptance snapshot Phase 1)`.

- [ ] **Step 4: Verify tĩnh**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_eval_grader.py -q` → pass.
Run: `./.venv/Scripts/python.exe -c "import yaml, pathlib; d=yaml.safe_load(pathlib.Path('evals/scenarios/core.yaml').read_text(encoding='utf-8')); print(len(d), sum(1 for s in d if s.get('phase',0)<=1))"`
Expected: `18 17` (18 scenario, 17 chạy với phase 1).

- [ ] **Step 5: Commit**

```bash
git add backend/evals/grader.py backend/evals/scenarios/core.yaml backend/evals/run_evals.py backend/evals/README.md backend/tests/test_eval_grader.py
git commit -m "feat(evals): expected_no_tools + 3 scenario snapshot Phase 1 (default --phase 1)"
```

---

### Task 8: Verify e2e — eval Phase 1 vs baseline, latency, BASELINE + PROJECT_CONTEXT

**Files:**
- Modify: `backend/evals/BASELINE.md` (thêm section Phase 1)
- Modify: `PROJECT_CONTEXT.md` (repo root — thêm mốc)

**Interfaces:**
- Consumes: toàn bộ Task 1-7; stack local (postgres 5435, redis 6380, uvicorn, arq); LLM key trong `backend/.env`.
- Produces: baseline Phase 1 ghi lại làm mốc; acceptance §5: các câu snapshot trả lời đúng, **0 tool call (verify bằng trace)**, p50 latency < 4s.

- [ ] **Step 1: Full pytest**

Run (trong `backend/`): `./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: PASS toàn bộ (3 dashboard flaky chấp nhận nếu trong khung giờ lỗi ~23h-24h VN).

- [ ] **Step 2: Dựng stack + smoke 1 scenario snapshot**

```bash
docker compose up -d postgres redis
# nền 1: ./.venv/Scripts/python.exe -u -m uvicorn app.main:app --port 8000
# nền 2: ./.venv/Scripts/python.exe -u -m arq app.agent.worker.WorkerSettings
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -u -m evals.run_evals --only snapshot-tinh-hinh-du-an
```
Expected: PASS với `tools=[]`. Nếu model VẪN gọi tool (hành vi model, không phải bug hạ tầng): ghi nhận kết quả thật vào BASELINE — KHÔNG ép pass; nhưng kiểm tra trace/system trước để chắc snapshot ĐÃ được tiêm (nếu snapshot không có trong system → đó là bug hạ tầng, sửa trước).

- [ ] **Step 3: Full eval run**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -u -m evals.run_evals`
Expected: 17 scenario chạy (1 skip phase-2). So với baseline Phase 0 (13/14): các scenario cũ không được tụt (trừ khác biệt model-hành-vi ghi nhận được); 3 scenario snapshot lý tưởng PASS.

- [ ] **Step 4: Đo latency p50 các scenario snapshot (acceptance <4s)**

```bash
docker compose exec -T postgres psql -U app -d app -c "SELECT iterations, total_latency_ms, stop_reason FROM agent_traces ORDER BY created_at DESC LIMIT 20;"
```
Lấy `total_latency_ms` của các request snapshot (iterations=1, 0 tool) → ghi p50 vào BASELINE.

- [ ] **Step 5: Cập nhật BASELINE.md + PROJECT_CONTEXT.md**

`backend/evals/BASELINE.md` — thêm section:

```markdown
## Phase 1 — Workspace Snapshot (2026-07-20)

| Ngày | Model | Pass | Fail | Skip | Ghi chú |
|---|---|---|---|---|---|
| (điền) | (model_fast runtime) | ?/17 | ? | 1 | Sau snapshot. So Phase 0: ... |

- Scenario snapshot (0-tool): snapshot-tinh-hinh-du-an ?, snapshot-ai-dang-lam-gi ?, snapshot-hom-nay-co-gi ? — p50 latency: ? ms (acceptance <4000ms).
- Scenario cũ đổi kết quả so Phase 0 (nếu có): ...
- Deviation §5.2 đã chốt: lazy build-on-miss + TTL + invalidate tại agent choke point (không dùng worker nền/debounce arq).
```

(mọi dấu `?` PHẢI thay bằng số thật trước khi commit.)

`PROJECT_CONTEXT.md`: thêm mốc `- 2026-07-20: Phase 1 AI upgrade xong — workspace snapshot (snapshot_service: SQL aggregates + cache Redis TTL + cắt theo quyền, tiêm system prompt 2 block, invalidate sau write-tool); eval ?/17. Tiếp theo Phase 2 (propose_actions + resolver + toolset động).`

- [ ] **Step 6: Dọn dẹp + Commit**

Kill uvicorn/arq (giữ postgres/redis). Xóa file log tạm nếu có.

```bash
git add backend/evals/BASELINE.md PROJECT_CONTEXT.md
git commit -m "docs: baseline Phase 1 snapshot + cap nhat PROJECT_CONTEXT"
```

---

## Self-review đã chạy

- **Spec coverage §5:** 5.1 nội dung snapshot (projects/nhân sự/hôm nay) → Task 2+3 (mục directive ghi chú "sau Phase 3" trong spec — không làm); 5.2 builder không LLM + theo quyền → Task 2/3/4; refresh → Task 4+6 (deviation lazy+TTL+invalidate ghi rõ Global Constraints + BASELINE); nạp vào system sau instruction + cân nhắc cache → Task 5+6 (2 block); acceptance 0-tool + p50<4s → Task 7+8. §3 config `snapshot_ttl_seconds` → Task 1.
- **Type consistency:** `get_snapshot_text(db, actor, *, now)` thống nhất Task 4/6; `render_for_actor(data, actor_user_id, *, visible_projects, visible_tasks, visible_users, now)` thống nhất Task 3/4; data keys thống nhất Task 2/3 (liệt kê trong Interfaces Task 2); `SNAPSHOT_WRITE_TOOLS` thống nhất Task 6; store methods thống nhất Task 1/4.
- **Placeholder scan:** các dấu `?` chỉ nằm trong khung BASELINE Task 8 với chỉ dẫn tường minh "PHẢI thay bằng số thật" (pattern Phase 0).
- **Lưu ý reviewer:** test render dùng DATA dict tay (không qua builder) là CHỦ ĐÍCH — render phải chịu được data từ JSON round-trip; test orchestrator (Task 4) mới nối builder+render thật.
