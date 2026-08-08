# Stable Message/TaskUpdate/TaskComment Ordering — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Loại bỏ tie-break sai (`Message.id`/`TaskUpdate.id`/`TaskComment.id` — UUID ngẫu nhiên) khỏi mọi `order_by(created_at, id)` trong repo, thay bằng cột `seq` tăng dần thật (autoincrement), để thứ tự đọc lại luôn khớp thứ tự tạo thật kể cả khi nhiều dòng có `created_at` trùng nhau trong cùng transaction.

**Architecture:** Thêm cột `seq: Mapped[int]` (BigInteger, tự tăng, KHÔNG phải primary key — PK vẫn là UUID `id` như hiện tại) vào 3 model `Message`, `TaskUpdate`, `TaskComment`. Trên Postgres cần `Identity()` tường minh (autoincrement mặc định của SQLAlchemy chỉ áp dụng cho cột PK); trên SQLite (test, `create_all`) `Identity()` cũng hoạt động qua rowid-backed autoincrement. Migration Alembic backfill `seq` cho dữ liệu cũ theo đúng thứ tự `created_at, id` hiện tại (best-effort — không thể khôi phục thứ tự thật đã mất, nhưng không làm gì còn tệ hơn hiện trạng). Sau đó sửa 9 lệnh `order_by` (8 vị trí đã tìm + xác nhận lại lúc code) đổi tie-break từ `.id` sang `.seq`.

**Tech Stack:** SQLAlchemy 2.0 (Mapped/mapped_column), Alembic, FastAPI, pytest-asyncio, SQLite in-memory (test) / Postgres (prod).

## Global Constraints

- KHÔNG đổi kiểu `id` (vẫn UUID, vẫn PK) — `seq` là cột phụ hoàn toàn mới, không phá bất kỳ FK/quan hệ nào đang có.
- Test suite dùng `Base.metadata.create_all` từ chính model (`tests/conftest.py`) — model SQLAlchemy phải tự đủ để `seq` autoincrement đúng trên SQLite, không được chỉ đúng trên Postgres.
- Theo quy ước CLAUDE.md: mọi bảng phải có `workspace_id` — 3 bảng này đã có sẵn, không đổi.
- TDD bắt buộc: mỗi task viết test trước, thấy fail đúng lý do, rồi mới code.
- Mỗi task 1 commit riêng (theo CLAUDE.md).
- KHÔNG động vào `SearchUserOut`/các phần không liên quan (giữ đúng phạm vi bug này).

---

### Task 1: Thêm cột `seq` vào model Message, TaskUpdate, TaskComment + migration

**Files:**
- Modify: `backend/app/models.py` (class `Message` ~dòng 409-435, class `TaskUpdate` ~dòng 233-242, class `TaskComment` ~dòng 245-252)
- Create: migration mới qua `alembic revision --autogenerate` (tên file do Alembic sinh, ví dụ `xxxxxxxxxxxx_add_seq_ordering_column.py`)
- Test: `backend/tests/test_message_seq_column.py` (mới)

**Interfaces:**
- Consumes: import có sẵn `from sqlalchemy import BigInteger, Identity` cần thêm vào dòng import đầu `models.py`.
- Produces: `Message.seq: Mapped[int]`, `TaskUpdate.seq: Mapped[int]`, `TaskComment.seq: Mapped[int]` — dùng ở Task 2.

- [ ] **Step 1: Viết test thất bại xác nhận `seq` tự tăng đúng thứ tự insert, kể cả khi `created_at` trùng nhau**

```python
# backend/tests/test_message_seq_column.py
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import Conversation, Message, MessageRole, Task, TaskComment, TaskUpdate, Project, Role, User


async def _mk_conv(db):
    ws, user = uuid.uuid4(), uuid.uuid4()
    conv = Conversation(workspace_id=ws, user_id=user)
    db.add(conv)
    await db.flush()
    return conv


@pytest.mark.asyncio
async def test_message_seq_auto_increments_even_with_same_created_at(db_session):
    conv = await _mk_conv(db_session)
    same_ts = datetime.now(timezone.utc)
    m1 = Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                 role=MessageRole.user, content=[{"type": "text", "text": "a"}],
                 created_at=same_ts)
    db_session.add(m1)
    await db_session.flush()
    m2 = Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                 role=MessageRole.assistant, content=[{"type": "text", "text": "b"}],
                 created_at=same_ts)
    db_session.add(m2)
    await db_session.flush()
    m3 = Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                 role=MessageRole.user, content=[{"type": "text", "text": "c"}],
                 created_at=same_ts)
    db_session.add(m3)
    await db_session.commit()

    rows = (await db_session.execute(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.seq.asc())
    )).scalars().all()
    assert [r.content[0]["text"] for r in rows] == ["a", "b", "c"]
    assert rows[0].seq < rows[1].seq < rows[2].seq
```

- [ ] **Step 2: Chạy test, xác nhận fail vì `Message.seq` chưa tồn tại**

Run: `cd backend && python -m pytest tests/test_message_seq_column.py -v`
Expected: FAIL với `AttributeError: type object 'Message' has no attribute 'seq'` (hoặc lỗi tương đương lúc build câu `select`).

- [ ] **Step 3: Thêm cột `seq` vào 3 model**

Sửa dòng import đầu `backend/app/models.py`:

```python
from sqlalchemy import String, Boolean, ForeignKey, DateTime, Date, Enum, JSON, Uuid, Integer, Text, UniqueConstraint, Float, BigInteger, Identity
```

Trong `class Message` (sau dòng `is_seed`, trước `created_at` — vị trí không quan trọng, giữ style hiện có), thêm:

```python
    # Tie-break thứ tự đọc lại: created_at có thể TRÙNG NHAU giữa nhiều Message
    # ghi trong cùng transaction (vd assistant trả lời + tool_result gần như
    # đồng thời) — sort chỉ theo created_at rồi tie-break bằng `id` (UUID ngẫu
    # nhiên) có thể ĐẢO THỨ TỰ hội thoại thật khi gửi lên Anthropic, gây mất/gộp
    # nhầm message (xem app/agent/loop.py::_merge_consecutive_roles). `seq` tự
    # tăng theo đúng thứ tự INSERT thật, dùng làm tie-break duy nhất đáng tin.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=False), nullable=False,
                                     unique=True)
```

Trong `class TaskUpdate` (sau `content`/`percent`/`status`, trước `created_at`):

```python
    # Cùng lý do seq của Message — xem docstring ở đó.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=False), nullable=False,
                                     unique=True)
```

Trong `class TaskComment` (sau `content`, trước `created_at`):

```python
    # Cùng lý do seq của Message — xem docstring ở đó.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=False), nullable=False,
                                     unique=True)
```

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_message_seq_column.py -v`
Expected: PASS. (SQLite qua `create_all`/`Identity` map về `INTEGER PRIMARY KEY`-like autoincrement cho cột `Identity`; nếu SQLite báo lỗi vì `Identity` yêu cầu cột phải là PK, xem ghi chú xử lý ở Step 4b ngay dưới.)

- [ ] **Step 4b (chỉ chạy nếu Step 4 fail vì SQLite từ chối `Identity` trên cột non-PK):**

SQLite không hỗ trợ `IDENTITY`/`SERIAL` thật trên cột không phải PK. Nếu Step 4 báo lỗi kiểu `sqlite3.OperationalError` liên quan `AUTOINCREMENT`, đổi khai báo 3 cột `seq` sang dùng `Sequence` tường minh (portable cả 2 engine) thay vì `Identity`:

```python
    from sqlalchemy import Sequence
    seq: Mapped[int] = mapped_column(
        BigInteger, Sequence("message_seq", start=1), nullable=False, unique=True)
```

(tên sequence đổi tương ứng `task_update_seq`, `task_comment_seq` cho 2 bảng kia). SQLAlchemy tự tạo/dùng sequence qua `nextval()` trên Postgres và giả lập tăng dần trên SQLite bằng cách track trong metadata — đủ cho mục đích tie-break đơn điệu, không cần đúng liên tục không đứt quãng.

- [ ] **Step 5: Sinh migration Alembic**

Đảm bảo Postgres dev đang chạy (`docker compose up -d postgres redis` ở `backend/`), rồi:

```bash
cd backend
.venv\Scripts\activate
alembic revision --autogenerate -m "add seq ordering column to messages, task_updates, task_comments"
```

Mở file migration vừa sinh ra ở `backend/alembic/versions/`, kiểm tra nó có 3 lệnh `op.add_column(...)` cho `seq` (kiểu `sa.BigInteger()` + `Identity` hoặc `Sequence` tuỳ Step 4/4b) trên `messages`, `task_updates`, `task_comments`. **Autogenerate KHÔNG backfill dữ liệu cũ** — thêm thủ công vào `upgrade()`, TRƯỚC dòng thêm cột (Postgres không cho thêm cột `NOT NULL` không default vào bảng đã có dữ liệu mà không backfill trước) hoặc dùng pattern add-nullable-rồi-backfill-rồi-not-null:

```python
def upgrade() -> None:
    """Upgrade schema."""
    # 1. Thêm cột seq cho phép NULL trước (bảng đã có dữ liệu)
    op.add_column('messages', sa.Column('seq', sa.BigInteger(), nullable=True))
    op.add_column('task_updates', sa.Column('seq', sa.BigInteger(), nullable=True))
    op.add_column('task_comments', sa.Column('seq', sa.BigInteger(), nullable=True))

    # 2. Backfill seq theo đúng thứ tự (created_at, id) hiện tại — best-effort,
    #    không khôi phục được thứ tự thật đã mất cho các dòng created_at trùng
    #    nhau trong quá khứ, nhưng cho 1 thứ tự ỔN ĐỊNH từ nay trở đi (không còn
    #    đổi ngẫu nhiên giữa các lần query như id UUID).
    op.execute("""
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY created_at, id) AS rn
            FROM messages
        )
        UPDATE messages SET seq = ranked.rn FROM ranked WHERE messages.id = ranked.id
    """)
    op.execute("""
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY created_at, id) AS rn
            FROM task_updates
        )
        UPDATE task_updates SET seq = ranked.rn FROM ranked WHERE task_updates.id = ranked.id
    """)
    op.execute("""
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY created_at, id) AS rn
            FROM task_comments
        )
        UPDATE task_comments SET seq = ranked.rn FROM ranked WHERE task_comments.id = ranked.id
    """)

    # 3. Set NOT NULL + tạo sequence auto-tăng bắt đầu từ MAX(seq)+1 cho dòng mới
    op.alter_column('messages', 'seq', nullable=False)
    op.alter_column('task_updates', 'seq', nullable=False)
    op.alter_column('task_comments', 'seq', nullable=False)
    op.create_unique_constraint('uq_messages_seq', 'messages', ['seq'])
    op.create_unique_constraint('uq_task_updates_seq', 'task_updates', ['seq'])
    op.create_unique_constraint('uq_task_comments_seq', 'task_comments', ['seq'])
    op.execute("CREATE SEQUENCE IF NOT EXISTS messages_seq_seq OWNED BY messages.seq")
    op.execute("SELECT setval('messages_seq_seq', COALESCE((SELECT MAX(seq) FROM messages), 0) + 1, false)")
    op.execute("ALTER TABLE messages ALTER COLUMN seq SET DEFAULT nextval('messages_seq_seq')")
    op.execute("CREATE SEQUENCE IF NOT EXISTS task_updates_seq_seq OWNED BY task_updates.seq")
    op.execute("SELECT setval('task_updates_seq_seq', COALESCE((SELECT MAX(seq) FROM task_updates), 0) + 1, false)")
    op.execute("ALTER TABLE task_updates ALTER COLUMN seq SET DEFAULT nextval('task_updates_seq_seq')")
    op.execute("CREATE SEQUENCE IF NOT EXISTS task_comments_seq_seq OWNED BY task_comments.seq")
    op.execute("SELECT setval('task_comments_seq_seq', COALESCE((SELECT MAX(seq) FROM task_comments), 0) + 1, false)")
    op.execute("ALTER TABLE task_comments ALTER COLUMN seq SET DEFAULT nextval('task_comments_seq_seq')")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('messages', 'seq')
    op.drop_column('task_updates', 'seq')
    op.drop_column('task_comments', 'seq')
```

Nếu autogenerate đã tự sinh `Identity()` (không phải `Sequence` thủ công ở trên), điều chỉnh SQL backfill tương ứng cách Postgres quản lý identity sequence (`ALTER TABLE ... ALTER COLUMN seq RESTART WITH ...` thay vì `setval` thủ công) — kiểm tra bằng cách đọc chính xác nội dung autogenerate sinh ra trước khi thêm backfill.

- [ ] **Step 6: Áp migration lên Postgres dev, verify**

```bash
cd backend
.venv\Scripts\activate
alembic upgrade head
```

Verify: `docker compose exec postgres psql -U app -d app -c "SELECT id, seq, created_at FROM messages ORDER BY seq LIMIT 5;"` — cột `seq` phải có giá trị, không NULL.

- [ ] **Step 7: Chạy lại full test file + xác nhận không phá gì**

Run: `cd backend && python -m pytest tests/test_message_seq_column.py tests/test_load_history_queue.py -v`
Expected: tất cả PASS (test_load_history_queue vẫn fail ở task này — sẽ fix ở Task 2, đây chỉ verify cột `seq` hoạt động).

- [ ] **Step 8: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/*.py backend/tests/test_message_seq_column.py
git commit -m "feat(models): them cot seq tang dan cho Message/TaskUpdate/TaskComment lam tie-break on dinh"
```

---

### Task 2: Sửa 9 vị trí `order_by` dùng `seq` thay vì `id` làm tie-break

**Files:**
- Modify: `backend/app/agent/loop.py:233`
- Modify: `backend/app/agent/summarizer.py:87`
- Modify: `backend/app/api/chat.py:122`
- Modify: `backend/app/api/chat.py:218`
- Modify: `backend/app/services/report_service.py:39`
- Modify: `backend/app/services/session_service.py:67`
- Modify: `backend/app/services/skill_service.py:121`
- Modify: `backend/app/services/work_service.py:271`
- Modify: `backend/app/services/work_service.py:316`
- Test: `backend/tests/test_load_history_queue.py::test_load_history_gop_2_message_role_giong_nhau_lien_nhau` (đã tồn tại, hiện đang FAIL — dùng làm test xác nhận)

**Interfaces:**
- Consumes: `Message.seq`, `TaskUpdate.seq`, `TaskComment.seq` từ Task 1.
- Produces: không có API mới — hành vi nội bộ, không đổi contract HTTP.

- [ ] **Step 1: Xác nhận test hiện có đang FAIL đúng vì bug tie-break (đã điều tra ở phiên debug trước)**

Run: `cd backend && python -m pytest tests/test_load_history_queue.py::test_load_history_gop_2_message_role_giong_nhau_lien_nhau -v`
Expected: FAIL với `AssertionError: assert ['assistant', 'user'] == ['user', 'assistant', 'user']` (dòng `user` đầu bị mất do 3 dòng `user` liền kề bị gộp nhầm sau khi sort đảo thứ tự bởi tie-break `id` ngẫu nhiên).

- [ ] **Step 2: Sửa `app/agent/loop.py:233`**

Đổi:
```python
    rows = await db.execute(stmt.order_by(Message.created_at.asc(), Message.id.asc()))
```
thành:
```python
    rows = await db.execute(stmt.order_by(Message.created_at.asc(), Message.seq.asc()))
```

- [ ] **Step 3: Chạy test xác nhận PASS**

Run: `cd backend && python -m pytest tests/test_load_history_queue.py -v`
Expected: tất cả PASS, bao gồm `test_load_history_gop_2_message_role_giong_nhau_lien_nhau`.

- [ ] **Step 4: Sửa 8 vị trí còn lại (cùng thay `.id.asc()/.id.desc()` bằng `.seq.asc()/.seq.desc()`)**

`app/agent/summarizer.py:87`:
```python
    stmt = stmt.order_by(Message.created_at.asc(), Message.seq.asc())
```

`app/api/chat.py:122`:
```python
        stmt = stmt.order_by(Message.created_at.desc(), Message.seq.desc()).limit(limit)
```

`app/api/chat.py:218`:
```python
                            .order_by(Message.created_at.asc(), Message.seq.asc()))
```

`app/services/report_service.py:39`:
```python
        .order_by(TaskUpdate.created_at.desc(), TaskUpdate.seq.desc()).limit(1)
```

`app/services/session_service.py:67`:
```python
    ).order_by(Message.created_at.asc(), Message.seq.asc()))).scalars().all() if m.content]
```

`app/services/skill_service.py:121`:
```python
        .order_by(TaskUpdate.created_at.desc(), TaskUpdate.seq.desc()).limit(5))
```

`app/services/work_service.py:271`:
```python
                            .order_by(TaskUpdate.created_at.desc(), TaskUpdate.seq.desc()))
```

`app/services/work_service.py:316`:
```python
                             .order_by(TaskComment.created_at.asc(), TaskComment.seq.asc()))).scalars()
```

Trước khi sửa mỗi dòng, đọc 5 dòng context xung quanh bằng Read để xác nhận số dòng thật khớp (số dòng trong plan này có thể lệch nếu file đã đổi từ lúc viết plan tới lúc thực thi) — dùng Edit với `old_string` là dòng đầy đủ chứa `.id.asc()`/`.id.desc()` lấy từ Read, không đoán.

- [ ] **Step 5: Chạy full test suite**

Run: `cd backend && python -m pytest tests/ -v`
Expected: PASS toàn bộ, KHÔNG có test nào fail (baseline trước Task 1/2 là 836 passed, 1 failed — sau task này phải là 837+ passed, 0 failed liên quan tie-break; nếu vẫn có fail khác, xác nhận đó là pre-existing không liên quan bằng cách kiểm tra riêng, đừng mặc định coi là do thay đổi này).

- [ ] **Step 6: Export lại openapi.json (contract không đổi nhưng theo quy ước CLAUDE.md luôn chạy lại sau khi động vào code BE)**

```bash
cd backend
.venv\Scripts\activate
python scripts/export_openapi.py
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/agent/loop.py backend/app/agent/summarizer.py backend/app/api/chat.py backend/app/services/report_service.py backend/app/services/session_service.py backend/app/services/skill_service.py backend/app/services/work_service.py openapi.json
git commit -m "fix(order): dung seq thay id lam tie-break order_by created_at o 9 vi tri, tranh dao thu tu khi created_at trung nhau"
```

---

## Self-Review Notes

- **Spec coverage:** cả 9 vị trí `order_by(created_at, id)` tìm được qua grep đều có task sửa (Task 2, Step 2 + Step 4). Cột `seq` áp dụng đủ 3 bảng bị ảnh hưởng (`Message`, `TaskUpdate`, `TaskComment`).
- **Placeholder scan:** không còn "TBD"/"tương tự Task N" — mọi dòng sửa đã viết nguyên văn.
- **Type consistency:** `seq: Mapped[int]` nhất quán tên/kiểu giữa Task 1 (định nghĩa) và Task 2 (sử dụng `.seq.asc()/.desc()`).
- **Rủi ro còn lại (không thuộc phạm vi plan này, ghi nhận cho minh bạch):** backfill Step 5/Task 1 dùng `ROW_NUMBER() OVER (ORDER BY created_at, id)` — với dữ liệu **quá khứ** đã có tie-break sai, backfill này chỉ tạo ra thứ tự ổn định mới, KHÔNG khôi phục được thứ tự tạo thật đã mất (không có cách nào khôi phục vì thông tin đó chưa từng được lưu). Đây là giới hạn chấp nhận được — mục tiêu là chặn đứng lỗi từ nay trở đi, không phải sửa lịch sử.
