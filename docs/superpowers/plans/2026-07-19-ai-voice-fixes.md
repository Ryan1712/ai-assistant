# Fix lỗi AI chat + Voice notes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sửa toàn bộ lỗi logic/UX của pipeline AI chat và ghi âm đã tìm ra trong review 2026-07-19 (giờ VN cho agent, confirm card đầy đủ, hàng đợi không lọt ngữ cảnh, giới hạn history, prompt caching, markdown, auto-title, voice preview/hủy/xóa/tags, transcribe bất đồng bộ + re-transcribe).

**Architecture:** BE giữ nguyên phân tầng router→service→model; mọi thay đổi agent nằm trong `app/agent/*` + `app/services/*`. Voice chuyển transcribe từ đồng-bộ-lúc-upload sang arq job bất đồng bộ với cột `transcript_status`. FE giữ pattern hiện có (screen tự quản state, api layer mỏng).

**Tech Stack:** FastAPI + SQLAlchemy 2 async + arq + Anthropic SDK (BE); Expo 57 / RN 0.86 + expo-audio (FE). Thêm dependency FE: `react-native-markdown-display`.

## Global Constraints

- Mọi phản hồi/commit message: tiếng Việt không dấu ở subject (theo style repo: `fix(be): ...`, `feat(fe): ...`).
- TDD với backend: test trước, code sau. FE không có test runner → verification = `npx tsc --noEmit` (chạy trong `frontend/`).
- Mỗi task một commit. Kết thúc commit message bằng dòng: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Backend test chạy trong `backend/` với venv: `.venv\Scripts\activate` rồi `pytest tests/ -v` (hoặc `pytest tests/<file> -v` cho nhanh).
- KHÔNG dùng PowerShell `Get-Content | Set-Content` trên file có tiếng Việt — dùng tool Edit/Write.
- Đổi API contract (schemas/routes) → task cuối chạy `python scripts/export_openapi.py`.
- Alembic head hiện tại: `d1a99ee98bb8` (migration mới nối vào đây).
- Timezone VN: `timezone(timedelta(hours=7))` — dùng chung qua module mới `app/tz.py`.
- Branch làm việc: `fix/ai-voice-review` tạo từ HEAD hiện tại của `feature/task-comments-fe`.

**Setup trước Task 1:**
```bash
cd "d:/8. AI/ai-assistant" && git checkout -b fix/ai-voice-review
```

---

## PHẦN A — BACKEND AGENT/CHAT

### Task 1: Giờ Việt Nam + role/skill/ngôn ngữ trong system prompt

**Files:**
- Create: `backend/app/tz.py`
- Modify: `backend/app/agent/loop.py:18-38` (`_build_system_prompt`)
- Test: `backend/tests/test_system_prompt.py` (mới)

**Interfaces:**
- Produces: `app.tz.VN_TZ` (timezone UTC+7) — Task 2 dùng lại. `_build_system_prompt(actor, now: datetime | None = None)` nhận `now` để test.

- [ ] **Step 1: Viết test fail**

```python
# backend/tests/test_system_prompt.py
import uuid
from datetime import datetime, timezone

from app.agent.loop import _build_system_prompt
from app.models import Role, User


def _actor(role=Role.employee) -> User:
    return User(id=uuid.uuid4(), workspace_id=uuid.uuid4(), email="a@b.c",
                password_hash="x", full_name="Nam Test", role=role)


def test_prompt_gio_viet_nam():
    # 2026-07-19 18:30 UTC = 2026-07-20 01:30 VN (Thứ Hai)
    now = datetime(2026, 7, 19, 18, 30, tzinfo=timezone.utc)
    prompt = _build_system_prompt(_actor(), now=now)
    assert "2026-07-20" in prompt          # ngày theo VN, không phải UTC
    assert "01:30" in prompt               # có giờ, không chỉ ngày
    assert "Việt Nam" in prompt
    assert "Thứ Hai" in prompt


def test_prompt_co_role_va_huong_dan():
    prompt = _build_system_prompt(_actor(), now=datetime(2026, 7, 19, 4, 0, tzinfo=timezone.utc))
    assert "employee" in prompt
    assert "tiếng Việt" in prompt          # chỉ dẫn ngôn ngữ tường minh
    assert "use_skill" in prompt           # gợi ý dùng skill
    assert "CEO" in prompt                 # nêu ranh giới quyền chính
```

- [ ] **Step 2: Chạy để thấy fail**

Run: `pytest tests/test_system_prompt.py -v` — Expected: FAIL (assert "01:30"/"use_skill" không có).

- [ ] **Step 3: Implement**

```python
# backend/app/tz.py
"""Múi giờ Việt Nam dùng chung (UTC+7) — thị trường chính của app."""
from datetime import timedelta, timezone

VN_TZ = timezone(timedelta(hours=7))
```

Sửa `_build_system_prompt` trong `loop.py` (thay toàn bộ hàm; giữ nguyên phần còn lại của file):

```python
from app.tz import VN_TZ

_VN_WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]


def _build_system_prompt(actor: User, now: datetime | None = None) -> str:
    """System prompt theo từng request: danh tính actor lấy từ JWT (không bao giờ
    hỏi user ID), ngày GIỜ theo VN (user ở VN — 'hôm nay/ngày mai/3h chiều' đều
    là giờ VN), và thiên hướng hành động thay vì hỏi vặt."""
    now_vn = (now or datetime.now(timezone.utc)).astimezone(VN_TZ)
    weekday = _VN_WEEKDAYS[now_vn.weekday()]
    return (
        "Bạn là trợ lý AI quản lý công việc của công ty. "
        "Luôn trả lời bằng tiếng Việt (trừ khi người dùng chủ động dùng ngôn ngữ khác).\n"
        f"Người đang nói chuyện với bạn: {actor.full_name} "
        f"(id: {actor.id}, vai trò: {actor.role.value}). "
        "Khi người dùng nói 'tôi'/'của tôi'/'cho tôi' thì chính là người này — dùng id ở trên, "
        "TUYỆT ĐỐI không hỏi lại user ID.\n"
        f"Bây giờ là {weekday}, {now_vn:%Y-%m-%d} {now_vn:%H:%M} giờ Việt Nam (UTC+7). "
        "Mọi mốc thời gian người dùng nói ('hôm nay', 'ngày mai', '3h chiều') hiểu theo giờ VN.\n"
        "Ranh giới quyền chính: tạo/sửa/giao task & project, quản lý skill/instruction/"
        "lịch báo cáo/tài khoản là việc của CEO. Nếu người dùng không phải CEO mà nhờ các việc "
        "đó, đừng gọi tool — báo họ nhờ CEO thực hiện.\n"
        "Người dùng có thể được cấp 'skill' (quy trình/tri thức riêng của công ty): khi yêu cầu "
        "liên quan tới quy trình nội bộ, hãy tra list_skills rồi use_skill để lấy hướng dẫn.\n"
        "Thực hiện yêu cầu bằng cách gọi tool phù hợp. Khi đủ thông tin bắt buộc thì hành động "
        "ngay và chọn mặc định hợp lý cho tham số tùy chọn, đừng hỏi vặt. Thiếu thông tin thì "
        "ưu tiên tự tra bằng tool list (project/task/người) trước khi hỏi người dùng. "
        "Nếu tool trả về error, báo lại rõ ràng cho người dùng, không tự suy diễn hoặc chọn "
        "đối tượng thay thế. Với hành động nhạy cảm (khóa/mở tài khoản, "
        "gửi email, xóa instruction): GỌI TOOL NGAY — hệ thống tự dừng lại và hiện nút "
        "xác nhận cho người dùng; đừng tự hỏi xác nhận bằng lời trong chat."
    )
```

Lưu ý: câu "Đừng tự thẩm vấn quyền hạn" cũ bị THAY bằng đoạn "Ranh giới quyền chính" (tránh mâu thuẫn: giờ model được biết trước ranh giới CEO để khỏi đốt vòng tool vô ích; các quyền chi tiết hơn vẫn do service enforce).

- [ ] **Step 4: Chạy test pass + toàn bộ suite**

Run: `pytest tests/test_system_prompt.py -v` → PASS. Rồi `pytest tests/ -v` — nếu có test cũ assert chuỗi "Hôm nay là" / "(UTC)" thì sửa assertion đó theo prompt mới.

- [ ] **Step 5: Commit**

```bash
git add backend/app/tz.py backend/app/agent/loop.py backend/tests/test_system_prompt.py
git commit -m "fix(be): system prompt biet ngay GIO theo VN + ranh gioi quyen + goi y skill"
```

---

### Task 2: Lịch báo cáo nhập giờ Việt Nam

**Files:**
- Modify: `backend/app/services/report_schedule_service.py:20-28` (`compute_next_run`)
- Modify: `backend/app/agent/tools.py:446-451` (mô tả tool `create_report_schedule`)
- Test: thêm vào `backend/tests/test_report_schedule_service.py`

**Interfaces:**
- Consumes: `app.tz.VN_TZ` (Task 1).
- Produces: `compute_next_run(after, weekday, hour, minute)` — giữ nguyên chữ ký, nhưng `weekday/hour/minute` giờ hiểu theo **giờ VN**; trả về datetime UTC aware.

- [ ] **Step 1: Viết test fail**

```python
# thêm vào backend/tests/test_report_schedule_service.py
from datetime import datetime, timezone

from app.services.report_schedule_service import compute_next_run


def test_compute_next_run_hieu_gio_vn():
    # 02:00 UTC = 09:00 VN. Đặt 8h sáng → đã qua hôm nay (VN) → 8h VN ngày mai = 01:00 UTC ngày mai
    after = datetime(2026, 7, 19, 2, 0, tzinfo=timezone.utc)
    assert compute_next_run(after, weekday=None, hour=8, minute=0) == \
        datetime(2026, 7, 20, 1, 0, tzinfo=timezone.utc)


def test_compute_next_run_trong_ngay_vn():
    # 02:00 UTC = 09:00 VN. Đặt 10:30 VN → còn trong hôm nay = 03:30 UTC
    after = datetime(2026, 7, 19, 2, 0, tzinfo=timezone.utc)
    assert compute_next_run(after, weekday=None, hour=10, minute=30) == \
        datetime(2026, 7, 19, 3, 30, tzinfo=timezone.utc)


def test_compute_next_run_weekday_theo_vn():
    # 2026-07-19 18:00 UTC = Thứ Hai 01:00 VN (20/7). Đặt thứ Hai (0) 08:00 VN
    # → ngay hôm đó theo VN: 2026-07-20 01:00 UTC
    after = datetime(2026, 7, 19, 18, 0, tzinfo=timezone.utc)
    assert compute_next_run(after, weekday=0, hour=8, minute=0) == \
        datetime(2026, 7, 20, 1, 0, tzinfo=timezone.utc)
```

- [ ] **Step 2: Chạy fail** — `pytest tests/test_report_schedule_service.py -v` → 3 test mới FAIL.

- [ ] **Step 3: Implement**

```python
from app.tz import VN_TZ

def compute_next_run(after: datetime, weekday: int | None, hour: int, minute: int) -> datetime:
    """Lần chạy kế tiếp SAU `after` (không bao giờ trả về đúng `after`).

    weekday/hour/minute hiểu theo GIỜ VIỆT NAM (UTC+7) — CEO đặt '8h sáng thứ 2'
    là 8h VN chứ không phải 8h UTC (=15h VN). Trả về datetime UTC (DB lưu UTC).
    """
    if after.tzinfo is None:
        after = after.replace(tzinfo=timezone.utc)
    after_vn = after.astimezone(VN_TZ)
    candidate = after_vn.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= after_vn:
        candidate += timedelta(days=1)
    if weekday is not None:
        while candidate.weekday() != weekday:
            candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)
```

Sửa mô tả tool trong `tools.py` (chuỗi `"... Giờ theo UTC. VD ..."`):

```python
_register("create_report_schedule",
          "Đặt lịch tự động gửi báo cáo tiến độ định kỳ (chỉ CEO, gói Advanced). "
          "Tự tính weekday từ ngôn ngữ tự nhiên: 0=Thứ Hai...6=Chủ Nhật, để trống "
          "(null) nếu là hàng ngày. Giờ theo GIỜ VIỆT NAM (UTC+7). VD 'mỗi sáng "
          "thứ 2 lúc 8h' → weekday=0, hour=8, minute=0.", CreateReportScheduleToolIn,
          _create_report_schedule)
```

- [ ] **Step 4: Chạy pass** — `pytest tests/test_report_schedule_service.py tests/test_run_due_schedules.py tests/test_report_schedule_crud.py -v`. Test cũ nào assert theo giờ UTC (candidate cùng ngày UTC) sẽ fail → cập nhật expected của chúng theo ngữ nghĩa VN mới (cộng/trừ 7h).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/report_schedule_service.py backend/app/agent/tools.py backend/tests/
git commit -m "fix(be): lich bao cao hieu gio Viet Nam thay vi UTC"
```

---

### Task 3: Cron báo cáo bền vững — 1 lịch hỏng không giết cả cron

**Files:**
- Modify: `backend/app/services/report_schedule_service.py:81-102` (`run_due_schedules`)
- Test: thêm vào `backend/tests/test_run_due_schedules.py`

**Interfaces:**
- Produces: `run_due_schedules` giữ chữ ký; lỗi từng schedule bị nuốt (log + advance `next_run_at`), commit theo từng schedule.

- [ ] **Step 1: Viết test fail** — dựng dữ liệu theo đúng helper/fixture đang dùng sẵn trong `tests/test_run_due_schedules.py` (đọc file đó trước, tái dùng cách nó tạo workspace/CEO/schedule). Kịch bản:

```python
async def test_mot_lich_hong_khong_chan_lich_khac(db_session):
    # schedule1: creator bị hạ role xuống employee sau khi tạo lịch (require_ceo sẽ 403)
    # schedule2: creator vẫn là CEO
    # (dựng 2 workspace + 2 schedule theo helper sẵn có của file test này)
    ...
    results = await run_due_schedules(db_session, now=now)
    # Không raise; schedule2 vẫn ra báo cáo
    assert len(results) == 1
    # schedule1 vẫn được advance next_run_at để không retry mỗi phút mãi mãi
    await db_session.refresh(sched1)
    assert sched1.next_run_at > now
```

- [ ] **Step 2: Chạy fail** — hiện tại HTTPException 403 lan ra ngoài → test FAIL (raise).

- [ ] **Step 3: Implement** — thay `run_due_schedules`:

```python
import logging

logger = logging.getLogger(__name__)


async def run_due_schedules(db: AsyncSession, *, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    due_ids = [s.id for s in (await db.execute(select(ReportSchedule).where(
        ReportSchedule.active.is_(True), ReportSchedule.next_run_at <= now
    ))).scalars()]
    results = []
    for sched_id in due_ids:
        sched = await db.get(ReportSchedule, sched_id)
        if sched is None:
            continue
        try:
            actor = await db.get(User, sched.created_by)
            if actor is not None:
                out = await report_service.generate_report(
                    db, actor, project_id=sched.project_id, assignee_id=sched.assignee_id,
                    status=sched.status)
                await notify(db, workspace_id=sched.workspace_id,
                            recipient_id=sched.recipient_id, type="scheduled_report",
                            payload={"report_id": out["report_id"], "summary": out["summary"],
                                     "schedule_id": str(sched.id)})
                results.append({"schedule_id": str(sched.id), "report_id": out["report_id"]})
        except Exception:
            # 1 lịch hỏng (creator mất quyền CEO, project bị xóa...) không được kéo
            # sập cả cron chạy-mỗi-phút; vẫn tiến next_run_at để không retry vô hạn.
            logger.exception("report schedule %s failed", sched_id)
            await db.rollback()
            sched = await db.get(ReportSchedule, sched_id)
            if sched is None:
                continue
        sched.last_run_at = now
        sched.next_run_at = compute_next_run(now, sched.weekday, sched.hour, sched.minute)
        await db.commit()
    return results
```

- [ ] **Step 4: Chạy pass** — `pytest tests/test_run_due_schedules.py -v` → PASS toàn bộ.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/report_schedule_service.py backend/tests/test_run_due_schedules.py
git commit -m "fix(be): cron bao cao khong chet ca cum khi 1 lich hong"
```

---

### Task 4: Chặn tin nhắn rỗng + TTL cancel key khớp job_timeout

**Files:**
- Modify: `backend/app/schemas.py:326-327, 353-354` (`MessageSendIn`, `ChatRequestEditIn`)
- Modify: `backend/app/api/chat.py:137, 180` (TTL)
- Test: `backend/tests/test_chat_validation.py` (mới)

**Interfaces:**
- Produces: `MessageSendIn.content` / `ChatRequestEditIn.content` strip + bắt buộc không rỗng, max 8000 ký tự. Hằng `_CANCEL_TTL = 600` trong `chat.py`.

- [ ] **Step 1: Test fail**

```python
# backend/tests/test_chat_validation.py
import pytest
from pydantic import ValidationError

from app.schemas import ChatRequestEditIn, MessageSendIn


@pytest.mark.parametrize("cls", [MessageSendIn, ChatRequestEditIn])
def test_content_rong_bi_tu_choi(cls):
    with pytest.raises(ValidationError):
        cls(content="")
    with pytest.raises(ValidationError):
        cls(content="   \n  ")


@pytest.mark.parametrize("cls", [MessageSendIn, ChatRequestEditIn])
def test_content_bi_strip_va_gioi_han(cls):
    assert cls(content="  hello  ").content == "hello"
    with pytest.raises(ValidationError):
        cls(content="x" * 8001)
```

- [ ] **Step 2: Chạy fail** — `pytest tests/test_chat_validation.py -v` → FAIL.

- [ ] **Step 3: Implement** — trong `schemas.py` (đảm bảo `field_validator` đã được import từ pydantic; nếu chưa: `from pydantic import BaseModel, Field, field_validator`):

```python
class MessageSendIn(BaseModel):
    # Rỗng/toàn khoảng trắng → Anthropic từ chối text block rỗng → request failed;
    # chặn ngay từ API. Trần 8000 ký tự chống paste khổng lồ làm nổ context.
    content: str = Field(min_length=1, max_length=8000)

    @field_validator("content")
    @classmethod
    def _strip_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("content must not be blank")
        return v


class ChatRequestEditIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)

    @field_validator("content")
    @classmethod
    def _strip_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("content must not be blank")
        return v
```

Trong `chat.py`: thêm hằng gần đầu file và thay cả 2 chỗ `ex=300`:

```python
# TTL key hủy PHẢI >= arq job_timeout (600s, xem worker.py) — nếu nhỏ hơn, lệnh hủy
# có thể hết hạn trước khi loop kịp đọc trong 1 lượt stream dài.
_CANCEL_TTL = 600
```
→ `await redis.set(f"cancel:{req.id}", "1", ex=_CANCEL_TTL)` (cả `stop_all` lẫn `cancel_request`).

- [ ] **Step 4: Chạy pass** — `pytest tests/test_chat_validation.py -v` rồi `pytest tests/ -v` (test nào gửi content rỗng sẽ lộ ra — sửa test đó gửi content thật).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/api/chat.py backend/tests/test_chat_validation.py
git commit -m "fix(be): chan tin nhan rong + TTL cancel khop job_timeout"
```

---

### Task 5: Tool lỗi bất ngờ không giết request + xử lý max_tokens

**Files:**
- Modify: `backend/app/agent/tools.py:58-70` (`call_tool`)
- Modify: `backend/app/agent/llm_client.py:67` (max_tokens 8192)
- Modify: `backend/app/agent/loop.py` (nhánh kết thúc lượt)
- Test: `backend/tests/test_call_tool_errors.py` (mới) + thêm case vào test loop hiện có

**Interfaces:**
- Produces: `call_tool` không bao giờ raise vì lỗi trong handler — mọi Exception → `{"error": "tool_failed", "message": ...}`. `AnthropicLLMClient` default `max_tokens=8192`. Loop: khi `stop_reason == "max_tokens"` nối cảnh báo cắt cụt vào text + publish token.

- [ ] **Step 1: Test fail**

```python
# backend/tests/test_call_tool_errors.py
import uuid

import pytest
from pydantic import BaseModel

from app.agent import tools as tools_mod
from app.agent.tools import ToolSpec, call_tool
from app.models import Role, User


@pytest.fixture
def actor():
    return User(id=uuid.uuid4(), workspace_id=uuid.uuid4(), email="a@b.c",
                password_hash="x", full_name="A", role=Role.ceo)


class _NoArgs(BaseModel):
    pass


async def test_loi_bat_ngo_trong_handler_thanh_tool_result(actor, monkeypatch):
    async def boom(db, actor, body):
        raise ValueError("something exploded")
    monkeypatch.setitem(tools_mod.TOOLS, "boom_tool",
                        ToolSpec(name="boom_tool", description="", input_model=_NoArgs,
                                 handler=boom))
    result = await call_tool(None, actor, "boom_tool", {})
    assert result["error"] == "tool_failed"
    assert "something exploded" in result["message"]
```

- [ ] **Step 2: Chạy fail** — `pytest tests/test_call_tool_errors.py -v` → FAIL (ValueError raise thẳng).

- [ ] **Step 3: Implement**

`tools.py` — thêm nhánh except cuối vào `call_tool`:

```python
    try:
        return await spec.handler(db, actor, parsed)
    except HTTPException as exc:
        label = _ERROR_LABELS.get(exc.status_code, "error")
        message = _ERROR_MESSAGES.get(exc.status_code, str(exc.detail))
        return {"error": label, "message": message}
    except Exception as exc:  # noqa: BLE001
        # Lỗi lập trình/hạ tầng trong 1 tool không được giết cả request — trả về
        # tool_result lỗi để model tự báo lại/thử cách khác.
        return {"error": "tool_failed",
                "message": f"Tool gặp lỗi hệ thống ({type(exc).__name__}): {exc}"}
```

`llm_client.py:67`: `def __init__(self, client, model: str, max_tokens: int = 8192):`

`loop.py` — ngay sau vòng `async for event ...` (sau khi có `done`), trước khi build `assistant_content`:

```python
            if done.stop_reason == "max_tokens":
                # Trả lời bị cắt vì chạm trần output — nói thẳng cho người dùng
                # thay vì im lặng như thể đã trả lời xong.
                cut_note = ("\n\n⚠️ Câu trả lời đã chạm giới hạn độ dài và bị cắt — "
                            "nhắn 'viết tiếp' để xem phần còn lại.")
                text_parts.append(cut_note)
                await publisher.publish(req.conversation_id,
                                        {"type": "token", "chat_request_id": str(req.id),
                                         "text": cut_note})
```

- [ ] **Step 4: Chạy pass** — `pytest tests/test_call_tool_errors.py tests/ -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/tools.py backend/app/agent/llm_client.py backend/app/agent/loop.py backend/tests/test_call_tool_errors.py
git commit -m "fix(be): tool loi bat ngo khong giet request + bao ro khi tra loi bi cat (max_tokens 8192)"
```

---

### Task 6: Hàng đợi thật — tin queued không lọt vào ngữ cảnh request đang chạy

**Files:**
- Modify: `backend/app/agent/loop.py:52-59` (`_load_history`) + call site `:113`
- Test: `backend/tests/test_load_history_queue.py` (mới)

**Interfaces:**
- Produces: `_load_history(db, conversation_id, current_request_id)` — loại message của các request đang `queued` (và `cancelled` chưa từng chạy) KHÁC request hiện tại. Nhờ đó "ưu tiên" (reorder) cũng có tác dụng thật: request nào chạy trước thì message của nó vào ngữ cảnh trước.

- [ ] **Step 1: Test fail**

```python
# backend/tests/test_load_history_queue.py
import uuid

from app.agent.loop import _load_history
from app.models import ChatRequest, ChatRequestStatus, Conversation, Message, MessageRole


async def _mk_conv(db):
    ws, user = uuid.uuid4(), uuid.uuid4()
    conv = Conversation(workspace_id=ws, user_id=user)
    db.add(conv)
    await db.flush()
    return conv


async def _mk_req(db, conv, content, pos, status=ChatRequestStatus.queued):
    req = ChatRequest(workspace_id=conv.workspace_id, conversation_id=conv.id,
                      user_id=conv.user_id, content=content, queue_position=pos,
                      status=status)
    db.add(req)
    await db.flush()
    db.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                   chat_request_id=req.id, role=MessageRole.user,
                   content=[{"type": "text", "text": content}]))
    return req


async def test_tin_queued_khac_khong_lot_vao_history(db_session):
    conv = await _mk_conv(db_session)
    req1 = await _mk_req(db_session, conv, "tin 1", 1.0)
    await _mk_req(db_session, conv, "tin 2 (cho xu ly)", 2.0)
    await db_session.commit()

    history = await _load_history(db_session, conv.id, req1.id)
    texts = [b["text"] for m in history for b in m["content"] if b.get("type") == "text"]
    assert "tin 1" in texts
    assert all("tin 2" not in t for t in texts)


async def test_tin_da_xong_van_trong_history(db_session):
    conv = await _mk_conv(db_session)
    await _mk_req(db_session, conv, "tin cu da xong", 1.0, status=ChatRequestStatus.done)
    req2 = await _mk_req(db_session, conv, "tin moi", 2.0)
    await db_session.commit()

    history = await _load_history(db_session, conv.id, req2.id)
    texts = [b["text"] for m in history for b in m["content"] if b.get("type") == "text"]
    assert "tin cu da xong" in texts and "tin moi" in texts
```

- [ ] **Step 2: Chạy fail** — `pytest tests/test_load_history_queue.py -v` → FAIL (TypeError thiếu tham số / "tin 2" lọt vào).

- [ ] **Step 3: Implement** — thay `_load_history` (import thêm `and_, or_` từ sqlalchemy):

```python
async def _load_history(db: AsyncSession, conversation_id: uuid.UUID,
                        current_request_id: uuid.UUID) -> list[dict]:
    """Lịch sử hội thoại CHO 1 request đang chạy: loại message của các request còn
    đang xếp hàng (và cancelled chưa từng chạy) — nếu không, model đang trả lời tin 1
    đã 'nhìn thấy' tin 2, 3... chưa xử lý và trả lời gộp/nhầm; reorder cũng vô nghĩa."""
    skip_ids = select(ChatRequest.id).where(
        ChatRequest.conversation_id == conversation_id,
        ChatRequest.id != current_request_id,
        or_(ChatRequest.status == ChatRequestStatus.queued,
            and_(ChatRequest.status == ChatRequestStatus.cancelled,
                 ChatRequest.started_at.is_(None))),
    ).scalar_subquery()
    rows = await db.execute(
        select(Message).where(
            Message.conversation_id == conversation_id,
            or_(Message.chat_request_id.is_(None),
                Message.chat_request_id.not_in(skip_ids)),
        ).order_by(Message.created_at.asc(), Message.id.asc())
    )
    # Bỏ message content rỗng (dữ liệu cũ trước guard bên dưới) — Anthropic API
    # từ chối request có message rỗng.
    return [{"role": m.role.value, "content": m.content} for m in rows.scalars() if m.content]
```

Call site trong `run_agent_loop`: `history = await _load_history(db, req.conversation_id, req.id)`.

- [ ] **Step 4: Chạy pass** — `pytest tests/test_load_history_queue.py tests/ -v` (test agent loop cũ nào gọi `_load_history` 2 tham số thì cập nhật).

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/loop.py backend/tests/test_load_history_queue.py
git commit -m "fix(be): tin nhan trong hang doi khong lot vao ngu canh request dang chay"
```

---

### Task 7: Giới hạn history + giới hạn instruction

**Files:**
- Modify: `backend/app/agent/loop.py` (`_load_history` — cắt đuôi an toàn)
- Modify: `backend/app/services/instruction_service.py` (`active_instructions_text` — cap độ dài)
- Test: thêm vào `backend/tests/test_load_history_queue.py` + `backend/tests/test_instructions.py` (hoặc file instruction test hiện có)

**Interfaces:**
- Produces: hằng `MAX_HISTORY_MESSAGES = 80` (loop.py); history luôn bắt đầu bằng user-text-message (không bao giờ mở đầu bằng tool_result). `active_instructions_text` cắt còn tối đa `_MAX_CHARS = 8000` ký tự kèm dòng ghi chú khi bị cắt.

- [ ] **Step 1: Test fail**

```python
# thêm vào backend/tests/test_load_history_queue.py
from app.agent.loop import MAX_HISTORY_MESSAGES


async def test_history_bi_cat_va_bat_dau_bang_user_text(db_session):
    conv = await _mk_conv(db_session)
    req = None
    for i in range(MAX_HISTORY_MESSAGES + 20):
        req = await _mk_req(db_session, conv, f"tin {i}", float(i),
                            status=ChatRequestStatus.done)
        db_session.add(Message(workspace_id=conv.workspace_id, conversation_id=conv.id,
                               chat_request_id=req.id, role=MessageRole.assistant,
                               content=[{"type": "text", "text": f"tra loi {i}"}]))
    await db_session.commit()

    history = await _load_history(db_session, conv.id, req.id)
    assert len(history) <= MAX_HISTORY_MESSAGES
    first = history[0]
    assert first["role"] == "user"
    assert first["content"][0]["type"] == "text"
```

```python
# test cap instruction (đặt cạnh test instruction hiện có)
async def test_active_instructions_bi_cap_do_dai(db_session):
    # tạo workspace + CEO + 1 instruction content dài 20000 ký tự theo helper sẵn có
    ...
    text = await instruction_service.active_instructions_text(db_session, ws_id)
    assert len(text) <= 8000 + 100  # 8000 + dòng ghi chú bị cắt
    assert "bị cắt" in text
```

- [ ] **Step 2: Chạy fail.**

- [ ] **Step 3: Implement**

`loop.py` — thêm hằng cạnh `MAX_ITERATIONS` và đoạn cắt ở cuối `_load_history` (trước `return` hiện tại, đổi return thành xử lý qua biến):

```python
# Trần số message nạp vào ngữ cảnh — hội thoại dài không giới hạn sẽ (1) phình token
# gần bậc hai theo vòng tool, (2) tới lúc vượt context window thì MỌI tin nhắn sau đó
# của conversation đều fail vĩnh viễn.
MAX_HISTORY_MESSAGES = 80
```

```python
    msgs = [{"role": m.role.value, "content": m.content} for m in rows.scalars() if m.content]
    if len(msgs) > MAX_HISTORY_MESSAGES:
        msgs = msgs[-MAX_HISTORY_MESSAGES:]
        # Không được mở đầu bằng tool_result mồ côi (thiếu tool_use đi trước) —
        # trượt tới user message thuần text đầu tiên.
        start = next((i for i, m in enumerate(msgs)
                      if m["role"] == "user" and m["content"]
                      and m["content"][0].get("type") == "text"), None)
        msgs = msgs[start:] if start is not None else msgs[-1:]
    return msgs
```

`instruction_service.py` — trong `active_instructions_text`, sau khi join:

```python
_MAX_CHARS = 8000  # instruction nối thẳng vào system prompt MỌI request của MỌI nhân viên


# cuối hàm, thay `return joined`:
    if len(joined) > _MAX_CHARS:
        joined = joined[:_MAX_CHARS] + "\n\n(Chỉ dẫn quá dài — phần sau đã bị cắt.)"
    return joined
```

(Đọc hàm hiện tại trước khi sửa — giữ nguyên logic query, chỉ thêm cap ở bước cuối.)

- [ ] **Step 4: Chạy pass** — `pytest tests/test_load_history_queue.py tests/ -v`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/loop.py backend/app/services/instruction_service.py backend/tests/
git commit -m "fix(be): tran 80 message history + cap 8000 ky tu instruction, hoi thoai dai khong chet nua"
```

---

### Task 8: Bật prompt caching

**Files:**
- Modify: `backend/app/agent/llm_client.py` (`AnthropicLLMClient.stream`)
- Test: `backend/tests/test_llm_client_cache.py` (mới)

**Interfaces:**
- Produces: payload gửi Anthropic có `system` dạng block list với `cache_control: {"type": "ephemeral"}` và tool cuối cùng có `cache_control`. Interface `LLMClient.stream(system: str, ...)` không đổi (chuyển đổi nội bộ).

- [ ] **Step 1: Test fail**

```python
# backend/tests/test_llm_client_cache.py
from app.agent.llm_client import AnthropicLLMClient


class _FakeMessages:
    def __init__(self):
        self.kwargs = None

    async def create(self, **kwargs):
        self.kwargs = kwargs

        async def _empty():
            if False:
                yield  # pragma: no cover
        return _empty()


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessages()


async def test_cache_control_duoc_set():
    fake = _FakeClient()
    llm = AnthropicLLMClient(fake, model="claude-haiku-4-5")
    async for _ in llm.stream(system="sys", messages=[], tools=[
            {"name": "a", "description": "", "input_schema": {}},
            {"name": "b", "description": "", "input_schema": {}}]):
        pass
    kw = fake.messages.kwargs
    assert kw["system"] == [{"type": "text", "text": "sys",
                             "cache_control": {"type": "ephemeral"}}]
    assert "cache_control" not in kw["tools"][0]
    assert kw["tools"][-1]["cache_control"] == {"type": "ephemeral"}
```

- [ ] **Step 2: Chạy fail.**

- [ ] **Step 3: Implement** — trong `stream()`, thay phần build call:

```python
        # Prompt caching: system prompt + ~44 tool schema giống hệt nhau giữa các
        # lượt — không cache thì mỗi vòng tool trả tiền input đầy đủ cho toàn bộ.
        # cache_control đặt ở block cuối của mỗi vùng (system, tools) theo API Anthropic.
        system_payload = [{"type": "text", "text": system,
                           "cache_control": {"type": "ephemeral"}}]
        tools_payload = list(tools)
        if tools_payload:
            tools_payload = tools_payload[:-1] + [
                {**tools_payload[-1], "cache_control": {"type": "ephemeral"}}]

        resp = await self._client.messages.create(
            model=self._model, max_tokens=self._max_tokens,
            system=system_payload, messages=messages, tools=tools_payload,
            tool_choice={"type": "auto", "disable_parallel_tool_use": True},
            stream=True,
        )
```

- [ ] **Step 4: Chạy pass** — `pytest tests/test_llm_client_cache.py tests/ -v`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/llm_client.py backend/tests/test_llm_client_cache.py
git commit -m "feat(be): bat prompt caching cho system prompt + tool schemas"
```

---

### Task 9: Tự đặt tên hội thoại từ tin nhắn đầu

**Files:**
- Modify: `backend/app/api/chat.py` (`send_message`)
- Test: thêm vào file test chat API hiện có (grep `send_message` trong `backend/tests/` để tìm — tái dùng fixture auth/arq-mock của file đó)

**Interfaces:**
- Produces: hội thoại `title is None` nhận title = 60 ký tự đầu của tin nhắn đầu tiên (gộp khoảng trắng).

- [ ] **Step 1: Test fail** (đặt trong file test chat API hiện có, dùng client + auth headers theo pattern của file):

```python
async def test_auto_title_tu_tin_nhan_dau(client, ...):
    conv = (await client.post("/api/v1/conversations", json={}, headers=h)).json()
    assert conv["title"] is None
    await client.post(f"/api/v1/conversations/{conv['id']}/messages",
                      json={"content": "Tao task lam slide quy 3 cho Nam nhe"}, headers=h)
    convs = (await client.get("/api/v1/conversations", headers=h)).json()
    assert convs[0]["title"] == "Tao task lam slide quy 3 cho Nam nhe"
```

- [ ] **Step 2: Chạy fail.**

- [ ] **Step 3: Implement** — trong `send_message`, sau khi tạo `req` + `Message`, trước `commit`:

```python
    if conv.title is None:
        # Tự đặt tên từ tin nhắn đầu — danh sách hội thoại toàn "chưa đặt tên" thì
        # không tìm lại được gì. Cắt 60 ký tự, gộp khoảng trắng.
        conv.title = " ".join(body.content.split())[:60]
```

- [ ] **Step 4: Chạy pass.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/chat.py backend/tests/
git commit -m "feat(be): tu dat ten hoi thoai tu tin nhan dau tien"
```

---

### Task 10: Bỏ hold-queue khi đóng socket + FE so khớp resume không dấu

**Files:**
- Modify: `backend/app/api/ws.py:62-66`
- Modify: `frontend/src/api/chat.ts` (thêm `isResumePhrase`)
- Modify: `frontend/app/(main)/chat.tsx:230`
- Test BE: cập nhật test nào đang assert hold-on-disconnect (grep `hold_queue_if_pending` trong `backend/tests/`)

**Interfaces:**
- Produces: đóng WS **không** hold queue nữa (AI làm nốt việc khi user rời màn/khóa máy — trước đây cứ rời màn chat là AI "treo"). `continuity.is_resume_phrase` + cờ `queue_held` GIỮ NGUYÊN để conversation đã held từ trước vẫn resume được. FE export `isResumePhrase(text: string): boolean` chuẩn hóa giống BE (lowercase, đ→d, bỏ dấu NFD, gộp space).

- [ ] **Step 1 (BE): Sửa ws.py** — thay khối `finally`:

```python
    finally:
        presence.disconnect(conversation_id)
        # KHÔNG hold queue khi socket đóng nữa: trên mobile, rời màn chat/khóa máy
        # là đóng WS — hold ở đây làm AI "tự treo" giữa chừng việc dài, người dùng
        # tưởng lỗi. Việc dang dở cứ chạy nốt; kết quả lưu DB, mở lại màn là thấy.
        # Cờ queue_held + cụm "tiếp tục công việc" giữ nguyên cho conversation đã
        # held từ trước (dữ liệu cũ).
```

Bỏ import `continuity` khỏi `ws.py` nếu không còn dùng. Chạy `pytest tests/ -v`; test nào assert "disconnect → queue_held=True" thì đổi thành assert ngược lại (không hold).

- [ ] **Step 2 (FE): chat.ts** — thêm dưới `RESUME_PHRASE`:

```ts
/** Chuẩn hóa giống BE (continuity._normalize): lowercase, đ→d, bỏ dấu, gộp space. */
export function isResumePhrase(text: string): boolean {
  const norm = text
    .toLowerCase()
    .replace(/đ/g, "d")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .split(/\s+/)
    .filter(Boolean)
    .join(" ");
  return norm === "tiep tuc cong viec";
}
```

- [ ] **Step 3 (FE): chat.tsx** — import `isResumePhrase` và thay dòng trong `submit`:

```ts
    if (held && isResumePhrase(content)) setHeld(false);
```

- [ ] **Step 4: Verify** — BE: `pytest tests/ -v` PASS. FE: `cd frontend && npx tsc --noEmit` sạch.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/ws.py backend/tests/ frontend/src/api/chat.ts "frontend/app/(main)/chat.tsx"
git commit -m "fix: bo hold queue khi dong socket (AI khong tu treo khi roi man) + FE khop cum resume khong dau"
```

---

## PHẦN B — FRONTEND CHAT

### Task 11: Confirm card hiển thị đầy đủ hành động + tham số

**Files:**
- Modify: `backend/app/schemas.py` (`ChatRequestOut` thêm `pending_action`)
- Modify: `frontend/src/api/chat.ts` (type `ChatRequest` thêm `pending_action`)
- Modify: `frontend/app/(main)/chat.tsx` (state `pendingConfirm`, handler WS, `refreshQueue`, render confirm card)

**Interfaces:**
- Produces: `ChatRequestOut.pending_action: dict | None` (chứa `tool_name`, `tool_input`, `tool_use_id`). FE `pendingConfirm: { requestId, toolName, toolInput } | null`.

- [ ] **Step 1 (BE):** thêm vào `ChatRequestOut`:

```python
class ChatRequestOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    status: ChatRequestStatus
    content: str
    # Cho FE khôi phục confirm card đầy đủ (tên tool + tham số) sau khi reload màn
    pending_action: dict | None = None
    created_at: dt.datetime

    model_config = {"from_attributes": True}
```

Test nhanh (thêm vào test chat API): sau khi request rơi vào `awaiting_confirmation` (dùng FakeLLMClient theo pattern test loop hiện có), GET `/requests` trả `pending_action.tool_name`. Nếu dựng kịch bản này quá rườm rà trong test API, chấp nhận assert schema: `ChatRequestOut.model_validate(req).pending_action` với `req` ORM có pending_action.

- [ ] **Step 2 (FE): chat.ts** — thêm vào type:

```ts
export type PendingAction = {
  tool_name: string;
  tool_input: Record<string, unknown>;
  tool_use_id: string;
};

export type ChatRequest = {
  id: string;
  conversation_id: string;
  status: ChatRequestStatus;
  content: string;
  pending_action: PendingAction | null;
  created_at: string;
};
```

- [ ] **Step 3 (FE): chat.tsx** — 4 chỗ:

(a) State:

```ts
const [pendingConfirm, setPendingConfirm] = useState<{
  requestId: string;
  toolName: string;
  toolInput: Record<string, unknown>;
} | null>(null);
```

(b) `refreshQueue` — thay dòng set generic:

```ts
const waiting = reqs.find((r) => r.status === "awaiting_confirmation");
if (waiting) {
  setPendingConfirm({
    requestId: waiting.id,
    toolName: waiting.pending_action?.tool_name ?? "unknown",
    toolInput: (waiting.pending_action?.tool_input ?? {}) as Record<string, unknown>,
  });
}
```

(c) WS handler `confirmation_required`:

```ts
setPendingConfirm({
  requestId: e.chat_request_id,
  toolName: e.tool_name,
  toolInput: (e.tool_input ?? {}) as Record<string, unknown>,
});
```

(d) Render confirm card — thay khối `{pendingConfirm && (...)}`:

```tsx
{pendingConfirm && (
  <View style={styles.confirmBar}>
    <Text style={{ fontWeight: "700", marginBottom: spacing.xs, color: colors.text }}>
      ⚠️ AI muốn: {labelForTool(pendingConfirm.toolName)}
    </Text>
    {Object.entries(pendingConfirm.toolInput).map(([k, v]) => (
      <Text key={k} style={{ color: colors.text }}>
        • {k}: {typeof v === "object" ? JSON.stringify(v) : String(v)}
      </Text>
    ))}
    <Text style={{ marginVertical: spacing.sm, color: colors.text }}>
      Xác nhận thực hiện?
    </Text>
    <View style={{ flexDirection: "row", gap: spacing.md }}>
      <TouchableOpacity style={styles.okBtn} onPress={() => resolveConfirm(true)}>
        <Text style={{ color: colors.onPrimary }}>Đồng ý</Text>
      </TouchableOpacity>
      <TouchableOpacity style={styles.denyBtn} onPress={() => resolveConfirm(false)}>
        <Text style={{ color: colors.onPrimary }}>Từ chối</Text>
      </TouchableOpacity>
    </View>
  </View>
)}
```

- [ ] **Step 4: Verify** — BE pytest PASS; FE `npx tsc --noEmit` sạch.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/tests/ frontend/src/api/chat.ts "frontend/app/(main)/chat.tsx"
git commit -m "fix: confirm card hien day du ten hanh dong + tham so (het duyet mu)"
```

---

### Task 12: FE không nuốt lỗi — submit giữ lại tin nhắn, lỗi thân thiện + nút gửi lại

**Files:**
- Modify: `frontend/app/(main)/chat.tsx` (`submit`, `resumeQueue`, `stopAll`/`cancelQueued`/`prioritize`, handler `request_failed`, Row type + renderItem)

**Interfaces:**
- Produces: Row có kind mới `"failed"` mang `retryContent`.

- [ ] **Step 1: Row type + helper lỗi**

```ts
type Row =
  | { key: string; kind: "user" | "assistant"; text: string }
  | { key: string; kind: "streaming"; text: string }
  | { key: string; kind: "system"; text: string }
  | { key: string; kind: "failed"; text: string; retryContent: string | null };

function friendlyError(raw: string): string {
  if (raw.includes("max_iterations_exceeded"))
    return "AI chạy quá nhiều bước mà chưa xong — thử chia nhỏ yêu cầu.";
  if (raw.includes("max_tokens")) return "Câu trả lời quá dài bị cắt.";
  return `Có lỗi khi xử lý (${raw.slice(0, 120)}).`;
}
```

- [ ] **Step 2: submit/resumeQueue có try/catch, giữ lại input khi lỗi**

```ts
const submit = async () => {
  if (!conversationId || !input.trim()) return;
  const content = input.trim();
  setInput("");
  try {
    const req = await sendMessage(conversationId, content);
    if (held && isResumePhrase(content)) setHeld(false);
    setRows((prev) => [...prev, { key: `u-${req.id}`, kind: "user", text: content }]);
    await refreshQueue(conversationId);
  } catch (e: any) {
    setInput(content); // không được làm mất chữ người dùng vừa gõ
    setRows((prev) => [
      ...prev,
      { key: `senderr-${Date.now()}`, kind: "system",
        text: `⚠️ Gửi thất bại (${String(e?.message ?? e).slice(0, 80)}) — nội dung đã được giữ lại trong ô nhập.` },
    ]);
  }
};

const resumeQueue = async () => {
  if (!conversationId) return;
  try {
    const req = await sendMessage(conversationId, RESUME_PHRASE);
    setHeld(false);
    setRows((prev) => [...prev, { key: `u-${req.id}`, kind: "user", text: RESUME_PHRASE }]);
    await refreshQueue(conversationId);
  } catch {
    setRows((prev) => [...prev,
      { key: `resumeerr-${Date.now()}`, kind: "system", text: "⚠️ Không gửi được — thử lại." }]);
  }
};
```

- [ ] **Step 3: request_failed → row "failed" + nút Gửi lại.** Cần content của request lỗi: giữ ref `contentByRequest = useRef<Map<string, string>>(new Map())`; set trong `submit` (`contentByRequest.current.set(req.id, content)`) và trong `refreshQueue` (`reqs.forEach((r) => contentByRequest.current.set(r.id, r.content))`). Handler:

```ts
} else if (e.type === "request_failed") {
  setRunningTool(null);
  const retryContent = contentByRequest.current.get(e.chat_request_id) ?? null;
  setRows((prev) => [
    ...prev,
    { key: `fail-${e.chat_request_id}`, kind: "failed",
      text: `⚠️ ${friendlyError(e.error)}`, retryContent },
  ]);
  refreshQueue(cid);
}
```

renderItem — trong bubble, sau `<Text>`:

```tsx
{item.kind === "failed" && item.retryContent && (
  <TouchableOpacity
    onPress={() => {
      setInput(item.retryContent!);
    }}
  >
    <Text style={{ color: colors.primary, fontWeight: "700", marginTop: spacing.xs }}>
      ↻ Gửi lại nội dung này
    </Text>
  </TouchableOpacity>
)}
```

(`kind === "failed"` style dùng chung `styles.systemBubble` — cập nhật điều kiện style trong renderItem: `item.kind === "system" || item.kind === "failed"` → systemBubble.)

- [ ] **Step 4: stopAll/cancel/prioritize không im lặng**

```ts
const [actionError, setActionError] = useState<string | null>(null);

const doStopAll = async () => {
  if (!conversationId) return;
  setActionError(null);
  try {
    await stopAll(conversationId);
    await refreshQueue(conversationId);
  } catch {
    setActionError("Không dừng được — thử lại.");
  }
};
```

`cancelQueued`/`prioritize`: thay `catch {}` bằng `catch { setActionError("Thao tác thất bại — thử lại."); }`. Nút "Dừng tất cả" gọi `doStopAll`. Render `<ErrorText error={actionError} />` ngay dưới queueBar.

- [ ] **Step 5: Verify + Commit** — `npx tsc --noEmit` sạch.

```bash
git add "frontend/app/(main)/chat.tsx"
git commit -m "fix(fe): chat khong nuot loi - giu lai tin khi gui fail, loi than thien + nut gui lai"
```

---

### Task 13: Render markdown cho câu trả lời AI

**Files:**
- Modify: `frontend/package.json` (dependency mới)
- Modify: `frontend/app/(main)/chat.tsx` (renderItem)

- [ ] **Step 1: Cài lib**

```bash
cd frontend && npm install react-native-markdown-display@^7.0.2
```

- [ ] **Step 2: Dùng trong renderItem** — assistant/streaming render Markdown, user/system giữ Text:

```tsx
import Markdown from "react-native-markdown-display";

const mdStyles = {
  body: { color: colors.text, fontSize: type.body.fontSize },
  code_inline: { backgroundColor: colors.surface, color: colors.text },
  fence: { backgroundColor: colors.surface, borderColor: colors.divider },
  table: { borderColor: colors.divider },
  link: { color: colors.primary },
} as const;
```

```tsx
renderItem={({ item }) => (
  <View style={[styles.bubble, item.kind === "user" ? styles.userBubble
      : item.kind === "system" || item.kind === "failed" ? styles.systemBubble : styles.aiBubble]}>
    {item.kind === "assistant" || item.kind === "streaming" ? (
      <Markdown style={mdStyles}>
        {item.text + (item.kind === "streaming" ? " ▍" : "")}
      </Markdown>
    ) : (
      <Text style={{ color: item.kind === "user" ? colors.onPrimary : colors.text }}>
        {item.text}
      </Text>
    )}
    {/* nút Gửi lại của Task 12 giữ nguyên dưới đây */}
  </View>
)}
```

- [ ] **Step 3: Verify + Commit** — `npx tsc --noEmit`; chạy `npx expo start --web` mở nhanh màn chat xác nhận không crash.

```bash
git add frontend/package.json frontend/package-lock.json "frontend/app/(main)/chat.tsx"
git commit -m "feat(fe): render markdown cho cau tra loi AI (bang, bullet, bold khong con hien raw)"
```

---

### Task 14: Dấu vết hành động khi reload + chỉ báo "AI đang soạn"

**Files:**
- Modify: `frontend/app/(main)/chat.tsx` (`loadHistory`, khu indicator)

- [ ] **Step 1: loadHistory render cả tool_use chips** — thay `loadHistory`:

```ts
const loadHistory = useCallback(async (cid: string) => {
  const msgs = await listMessages(cid);
  const out: Row[] = [];
  for (const m of msgs) {
    const text = textOfMessage(m);
    if (text) out.push({ key: m.id, kind: m.role === "user" ? "user" : "assistant", text });
    // Lượt AI thuần thao tác (tạo task, gán người...) không có text — trước đây
    // biến mất khỏi lịch sử, người dùng mất dấu "AI đã làm gì".
    const toolUses = m.content.filter((b) => b.type === "tool_use");
    for (const b of toolUses) {
      if (b.type === "tool_use")
        out.push({ key: `${m.id}-${b.id}`, kind: "system", text: `🔧 ${labelForTool(b.name)}` });
    }
  }
  setRows(out);
}, []);
```

- [ ] **Step 2: Chỉ báo "đang soạn"** — trước khu `{runningTool && ...}`:

```tsx
{running && !runningTool && !pendingConfirm && !streamingText.current.get(running.id) && (
  <View style={styles.toolBar}>
    <ActivityIndicator color={colors.primary} size="small" />
    <Text style={{ color: colors.textSecondary }}>AI đang soạn…</Text>
  </View>
)}
```

- [ ] **Step 3: Verify + Commit** — `npx tsc --noEmit`.

```bash
git add "frontend/app/(main)/chat.tsx"
git commit -m "feat(fe): giu dau vet tool khi mo lai hoi thoai + chi bao AI dang soan"
```

---

## PHẦN C — VOICE NOTES

### Task 15: Model + migration + upload mới (size limit, title, duration, status; bỏ transcribe đồng bộ)

**Files:**
- Modify: `backend/app/models.py:372-383` (VoiceNote)
- Create: `backend/alembic/versions/f0a1b2c3d4e5_voice_note_status_duration.py`
- Modify: `backend/app/services/voice_service.py` (`create_voice_note`, `_out`)
- Modify: `backend/app/api/voice_notes.py` (upload nhận field mới)
- Test: thêm vào file test voice hiện có (grep `create_voice_note` trong `backend/tests/`)

**Interfaces:**
- Produces: cột mới `title: str | None`, `duration_seconds: float | None`, `transcript_status: str` (`"pending"` = chưa có STT thật; `"queued"/"processing"/"done"/"failed"` khi có). `create_voice_note(..., title=None, duration_seconds=None)` KHÔNG transcribe nữa. `_out` trả thêm 3 field. `_MAX_FILE_SIZE = 25MB` → 413 `file_too_large`.

- [ ] **Step 1: Test fail**

```python
async def test_upload_khong_transcribe_dong_bo_va_co_field_moi(db_session, ...):
    out = await voice_service.create_voice_note(
        db_session, actor, filename="a.m4a", data=b"xxx",
        title="Hop giao ban", duration_seconds=12.5)
    assert out["transcript"] == ""
    assert out["transcript_status"] == "pending"   # stt_mock=True → chờ STT thật
    assert out["title"] == "Hop giao ban"
    assert out["duration_seconds"] == 12.5


async def test_upload_qua_25mb_bi_chan(db_session, ...):
    with pytest.raises(HTTPException) as ei:
        await voice_service.create_voice_note(db_session, actor, filename="a.m4a",
                                              data=b"0" * (25 * 1024 * 1024 + 1))
    assert ei.value.status_code == 413
```

- [ ] **Step 2: Chạy fail.**

- [ ] **Step 3: Implement**

`models.py` — thêm 3 cột vào `VoiceNote` (sau `language`):

```python
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    # pending = chưa có STT thật; queued/processing/done/failed khi transcribe async chạy
    transcript_status: Mapped[str] = mapped_column(String(16), default="pending",
                                                    server_default="pending")
```

(`Float` đã import ở đầu models.py cho ChatRequest.queue_position.)

Migration:

```python
"""voice note: title + duration + transcript_status

Revision ID: f0a1b2c3d4e5
Revises: d1a99ee98bb8
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'f0a1b2c3d4e5'
down_revision: Union[str, Sequence[str], None] = 'd1a99ee98bb8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('voice_notes', sa.Column('title', sa.String(255), nullable=True))
    op.add_column('voice_notes', sa.Column('duration_seconds', sa.Float(), nullable=True))
    op.add_column('voice_notes', sa.Column('transcript_status', sa.String(16),
                                           nullable=False, server_default='pending'))


def downgrade() -> None:
    op.drop_column('voice_notes', 'transcript_status')
    op.drop_column('voice_notes', 'duration_seconds')
    op.drop_column('voice_notes', 'title')
```

`voice_service.py`:

```python
_MAX_FILE_SIZE = 25 * 1024 * 1024  # attachment có trần 20MB; voice cho nhỉnh hơn


def _out(n: VoiceNote) -> dict:
    return {"id": str(n.id), "transcript": n.transcript, "language": n.language,
            "transcript_status": n.transcript_status,
            "title": n.title, "duration_seconds": n.duration_seconds,
            "tags": n.tags or [],
            "task_id": str(n.task_id) if n.task_id else None,
            "project_id": str(n.project_id) if n.project_id else None,
            "created_at": n.created_at}


async def create_voice_note(db: AsyncSession, actor: User, *, filename: str, data: bytes,
                            tags: list[str] | None = None,
                            task_id: uuid.UUID | None = None,
                            project_id: uuid.UUID | None = None,
                            title: str | None = None,
                            duration_seconds: float | None = None) -> dict:
    ext = Path(filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(422, "unsupported_audio_format")
    if len(data) > _MAX_FILE_SIZE:
        raise HTTPException(413, "file_too_large")
    if task_id is not None:
        await get_visible_task_or_404(db, actor, task_id)
    if project_id is not None and project_id not in await visible_project_ids(db, actor):
        raise HTTPException(404, "project_not_found")

    file_path = _voice_dir(actor.workspace_id) / f"{uuid.uuid4()}{ext}"
    file_path.write_bytes(data)
    # Transcribe KHÔNG chạy đồng bộ ở đây nữa: STT thật sẽ chậm, block upload.
    # Worker arq xử lý (Task 16); khi chưa có STT thật thì status=pending, có thể
    # re-transcribe sau qua POST /voice-notes/{id}/transcribe.
    status = "queued" if not get_settings().stt_mock else "pending"
    note = VoiceNote(workspace_id=actor.workspace_id, author_id=actor.id,
                     file_path=str(file_path), transcript="", language="und",
                     transcript_status=status, title=title,
                     duration_seconds=duration_seconds,
                     tags=tags or [], task_id=task_id, project_id=project_id)
    db.add(note)
    await db.commit()
    return _out(note)
```

`voice_notes.py` upload:

```python
@router.post("", status_code=201)
async def upload_voice_note(file: UploadFile = File(...), tags: str = Form(""),
                            title: str = Form(""),
                            duration_seconds: float | None = Form(None),
                            task_id: uuid.UUID | None = Form(None),
                            project_id: uuid.UUID | None = Form(None),
                            actor: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    data = await file.read()
    return await voice_service.create_voice_note(
        db, actor, filename=file.filename or "", data=data, tags=tag_list,
        title=title.strip() or None, duration_seconds=duration_seconds,
        task_id=task_id, project_id=project_id)
```

- [ ] **Step 4: Chạy pass** — `pytest tests/ -v` (test voice cũ nào assert transcribe đồng bộ → cập nhật: transcript luôn "" lúc upload, status pending). Chạy migration trên DB dev: `docker compose up -d postgres` + `alembic upgrade head` (nếu DB dev đang dùng).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/alembic/versions/f0a1b2c3d4e5_voice_note_status_duration.py backend/app/services/voice_service.py backend/app/api/voice_notes.py backend/tests/
git commit -m "feat(be): voice note co title/duration/transcript_status + tran 25MB, bo transcribe dong bo"
```

---

### Task 16: Transcribe bất đồng bộ (arq job) + endpoint re-transcribe

**Files:**
- Modify: `backend/app/services/voice_service.py` (thêm `transcribe_note`, `request_transcription`)
- Modify: `backend/app/agent/worker.py` (job `transcribe_voice_note`, đăng ký functions)
- Modify: `backend/app/api/voice_notes.py` (POST `/{id}/transcribe`, enqueue sau upload)
- Test: thêm vào file test voice

**Interfaces:**
- Produces: `voice_service.transcribe_note(db, voice_note_id)` — chạy STT, set transcript/language/status (`done`/`failed`); job arq `transcribe_voice_note(ctx, voice_note_id)`; route `POST /api/v1/voice-notes/{id}/transcribe` → 202 `{"status": "queued"}` hoặc 409 `stt_not_configured` khi `stt_mock=True`.

- [ ] **Step 1: Test fail**

```python
async def test_transcribe_note_cap_nhat_transcript(db_session, monkeypatch, ...):
    out = await voice_service.create_voice_note(db_session, actor, filename="a.m4a", data=b"x")

    class _Stub:
        async def transcribe(self, data, filename):
            return "xin chao ca nha", "vi"
    monkeypatch.setattr(voice_service, "get_transcription_client", lambda: _Stub())

    await voice_service.transcribe_note(db_session, uuid.UUID(out["id"]))
    note = await db_session.get(VoiceNote, uuid.UUID(out["id"]))
    assert note.transcript == "xin chao ca nha"
    assert note.language == "vi"
    assert note.transcript_status == "done"


async def test_transcribe_note_loi_thanh_failed(db_session, monkeypatch, ...):
    out = await voice_service.create_voice_note(db_session, actor, filename="a.m4a", data=b"x")

    class _Boom:
        async def transcribe(self, data, filename):
            raise RuntimeError("stt down")
    monkeypatch.setattr(voice_service, "get_transcription_client", lambda: _Boom())

    await voice_service.transcribe_note(db_session, uuid.UUID(out["id"]))
    note = await db_session.get(VoiceNote, uuid.UUID(out["id"]))
    assert note.transcript_status == "failed"
```

- [ ] **Step 2: Chạy fail.**

- [ ] **Step 3: Implement**

`voice_service.py`:

```python
async def transcribe_note(db: AsyncSession, voice_note_id: uuid.UUID) -> None:
    """Chạy STT cho 1 voice note (gọi từ arq job). Không raise — lỗi ghi status=failed."""
    note = await db.get(VoiceNote, voice_note_id)
    if note is None:
        return
    note.transcript_status = "processing"
    await db.commit()
    try:
        data = Path(note.file_path).read_bytes()
        transcript, language = await get_transcription_client().transcribe(
            data, Path(note.file_path).name)
        note.transcript = transcript
        note.language = language
        note.transcript_status = "done"
    except Exception:
        note.transcript_status = "failed"
    await db.commit()


async def request_transcription(db: AsyncSession, actor: User,
                                voice_note_id: uuid.UUID) -> dict:
    """User bấm 'nhận dạng lại' — chỉ khi có STT thật; đưa note về queued."""
    note = await _get_own_or_404(db, actor, voice_note_id)
    if get_settings().stt_mock:
        raise HTTPException(409, "stt_not_configured")
    note.transcript_status = "queued"
    await db.commit()
    return {"id": str(note.id), "status": "queued"}
```

`worker.py` — thêm job + đăng ký:

```python
from app.services import report_schedule_service, voice_service, work_service


async def transcribe_voice_note(ctx: dict, voice_note_id: uuid.UUID) -> None:
    """arq job: chạy STT cho 1 voice note (upload/re-transcribe enqueue)."""
    async with ctx["session_factory"]() as db:
        await voice_service.transcribe_note(db, voice_note_id)
```

`WorkerSettings.functions = [process_conversation, transcribe_voice_note]`.

`voice_notes.py` — dep arq + enqueue sau upload + route mới:

```python
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

async def get_arq_pool(request: Request):
    return request.app.state.arq_pool
```

Cuối `upload_voice_note` (thêm param `arq_pool=Depends(get_arq_pool)`):

```python
    out = await voice_service.create_voice_note(...)
    if out["transcript_status"] == "queued":
        await arq_pool.enqueue_job("transcribe_voice_note", uuid.UUID(out["id"]))
    return out
```

Route mới:

```python
@router.post("/{voice_note_id}/transcribe", status_code=202)
async def retranscribe_voice_note(voice_note_id: uuid.UUID,
                                  actor: User = Depends(get_current_user),
                                  db: AsyncSession = Depends(get_db),
                                  arq_pool=Depends(get_arq_pool)):
    out = await voice_service.request_transcription(db, actor, voice_note_id)
    await arq_pool.enqueue_job("transcribe_voice_note", voice_note_id)
    return out
```

- [ ] **Step 4: Chạy pass** — `pytest tests/ -v`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/voice_service.py backend/app/agent/worker.py backend/app/api/voice_notes.py backend/tests/
git commit -m "feat(be): transcribe bat dong bo qua arq + endpoint re-transcribe (ghi am cu khong mat gia tri khi co STT that)"
```

---

### Task 17: Xóa + sửa title/tags voice note

**Files:**
- Modify: `backend/app/services/voice_service.py`, `backend/app/api/voice_notes.py`, `backend/app/schemas.py`
- Test: thêm vào file test voice

**Interfaces:**
- Produces: `DELETE /api/v1/voice-notes/{id}` → 204 (author-only, xóa file best-effort); `PATCH /api/v1/voice-notes/{id}` body `{"title"?: str, "tags"?: list[str]}` → note mới. Schema `VoiceNotePatchIn`.

- [ ] **Step 1: Test fail**

```python
async def test_delete_voice_note(db_session, ...):
    out = await voice_service.create_voice_note(db_session, actor, filename="a.m4a", data=b"x")
    await voice_service.delete_voice_note(db_session, actor, uuid.UUID(out["id"]))
    assert await db_session.get(VoiceNote, uuid.UUID(out["id"])) is None


async def test_patch_title_tags(db_session, ...):
    out = await voice_service.create_voice_note(db_session, actor, filename="a.m4a", data=b"x")
    updated = await voice_service.update_voice_note(
        db_session, actor, uuid.UUID(out["id"]), title="Hop sang", tags=["hop", "sang"])
    assert updated["title"] == "Hop sang"
    assert updated["tags"] == ["hop", "sang"]


async def test_nguoi_khac_khong_xoa_duoc(db_session, ...):
    # actor2 cùng workspace nhưng khác author → 404
    ...
```

- [ ] **Step 2: Chạy fail.**

- [ ] **Step 3: Implement**

`voice_service.py`:

```python
async def delete_voice_note(db: AsyncSession, actor: User, voice_note_id: uuid.UUID) -> None:
    note = await _get_own_or_404(db, actor, voice_note_id)
    try:
        Path(note.file_path).unlink(missing_ok=True)  # file hỏng không chặn xóa row
    except OSError:
        pass
    await db.delete(note)
    await db.commit()


async def update_voice_note(db: AsyncSession, actor: User, voice_note_id: uuid.UUID, *,
                            title: str | None = None,
                            tags: list[str] | None = None) -> dict:
    note = await _get_own_or_404(db, actor, voice_note_id)
    if title is not None:
        note.title = title.strip() or None
    if tags is not None:
        note.tags = tags
    await db.commit()
    return _out(note)
```

`schemas.py`:

```python
class VoiceNotePatchIn(BaseModel):
    title: str | None = None
    tags: list[str] | None = None
```

`voice_notes.py`:

```python
@router.delete("/{voice_note_id}", status_code=204)
async def delete_voice_note(voice_note_id: uuid.UUID,
                            actor: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    await voice_service.delete_voice_note(db, actor, voice_note_id)


@router.patch("/{voice_note_id}")
async def patch_voice_note(voice_note_id: uuid.UUID, body: VoiceNotePatchIn,
                           actor: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    return await voice_service.update_voice_note(db, actor, voice_note_id,
                                                 title=body.title, tags=body.tags)
```

- [ ] **Step 4: Chạy pass** — `pytest tests/ -v`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/voice_service.py backend/app/api/voice_notes.py backend/app/schemas.py backend/tests/
git commit -m "feat(be): xoa + sua title/tags voice note (het rac vinh vien)"
```

---

### Task 18: FE ghi âm — preview, hủy, title/tags trước khi lưu, dọn recorder

**Files:**
- Modify: `frontend/src/api/voice.ts` (type + upload signature + delete/patch/retranscribe)
- Modify: `frontend/app/(main)/today.tsx` (QuickVoiceCard)
- Create: `frontend/src/util/format.ts` (formatDuration dùng chung)

**Interfaces:**
- Produces: `uploadVoiceNote(uri, opts?: { durationMs?; tags?: string[]; title?: string })`; `deleteVoiceNote(id)`, `patchVoiceNote(id, body)`, `retranscribeVoiceNote(id)`; `VoiceNote` type thêm `title/duration_seconds/transcript_status`; `formatDuration(ms)` từ `src/util/format.ts` (today.tsx và voice-notes.tsx cùng dùng).

- [ ] **Step 1: voice.ts**

```ts
export type VoiceNote = {
  id: string;
  transcript: string;
  language: string;
  transcript_status: "pending" | "queued" | "processing" | "done" | "failed";
  title: string | null;
  duration_seconds: number | null;
  tags: string[];
  task_id: string | null;
  project_id: string | null;
  created_at: string;
};

export const deleteVoiceNote = (id: string) =>
  apiFetch<void>(`/api/v1/voice-notes/${id}`, { method: "DELETE" });

export const patchVoiceNote = (id: string, body: { title?: string; tags?: string[] }) =>
  apiFetch<VoiceNote>(`/api/v1/voice-notes/${id}`, { method: "PATCH", body });

export const retranscribeVoiceNote = (id: string) =>
  apiFetch<{ id: string; status: string }>(`/api/v1/voice-notes/${id}/transcribe`, {
    method: "POST",
  });
```

`uploadVoiceNote` đổi chữ ký (giữ nguyên phần blob/webm-fix hiện có bên trong):

```ts
export const uploadVoiceNote = async (
  uri: string,
  opts: { durationMs?: number; tags?: string[]; title?: string } = {},
) => {
  const { durationMs, tags, title } = opts;
  const form = new FormData();
  // ... giữ nguyên nhánh web (fixWebmDuration dùng durationMs) và native hiện có ...
  if (tags && tags.length > 0) form.append("tags", tags.join(","));
  if (title) form.append("title", title);
  if (durationMs) form.append("duration_seconds", String(durationMs / 1000));
  return apiFetch<VoiceNote>("/api/v1/voice-notes", { method: "POST", body: form });
};
```

- [ ] **Step 2: format.ts** — move `formatDuration` từ today.tsx:

```ts
// frontend/src/util/format.ts
export function formatDuration(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const mm = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const ss = String(totalSeconds % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}
```

- [ ] **Step 3: QuickVoiceCard — luồng mới.** Bấm dừng KHÔNG upload ngay; chuyển sang trạng thái "chờ lưu": preview nghe lại + ô title + ô tags + nút Lưu/Hủy. Thay `toggle` + thêm state:

```tsx
type Pending = { uri: string; durationMs: number };

// trong QuickVoiceCard:
const [pending, setPending] = useState<Pending | null>(null);
const [draftTitle, setDraftTitle] = useState("");
const [draftTags, setDraftTags] = useState("");

const toggle = async () => {
  setError(null);
  try {
    if (recorderState.isRecording) {
      const durationMs = recorderState.durationMillis;
      await recorder.stop();
      if (recorder.uri) setPending({ uri: recorder.uri, durationMs });
      else setError("Không lấy được file ghi âm — thử lại.");
    } else {
      const perm = await AudioModule.requestRecordingPermissionsAsync();
      if (!perm.granted) {
        setError("Chưa được cấp quyền micro — bật trong Cài đặt để ghi âm.");
        return;
      }
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      await recorder.prepareToRecordAsync();
      recorder.record();
    }
  } catch {
    setError("Ghi âm thất bại — thử lại nhé.");
  }
};

const save = async () => {
  if (!pending) return;
  setBusy(true);
  setError(null);
  try {
    await uploadVoiceNote(pending.uri, {
      durationMs: pending.durationMs,
      title: draftTitle.trim() || undefined,
      tags: draftTags.split(",").map((t) => t.trim()).filter(Boolean),
    });
    setPending(null);
    setDraftTitle("");
    setDraftTags("");
    await loadNotes();
    setSaved(true);
    if (savedTimer.current) clearTimeout(savedTimer.current);
    savedTimer.current = setTimeout(() => setSaved(false), 2500);
  } catch {
    // GIỮ pending để bấm Lưu lại được — audio không mất khi upload lỗi
    setError("Tải lên thất bại — bấm Lưu để thử lại.");
  } finally {
    setBusy(false);
  }
};

const discard = () => {
  setPending(null);
  setDraftTitle("");
  setDraftTags("");
};
```

Preview component (đặt cùng file, mount có điều kiện để tránh hook lằng nhằng):

```tsx
function PendingPreview({ uri }: { uri: string }) {
  const player = useAudioPlayer({ uri });
  const status = useAudioPlayerStatus(player);
  return (
    <TouchableOpacity
      style={styles.recordBtn}
      onPress={() => (status.playing ? player.pause() : player.play())}
    >
      <Text style={{ color: colors.onPrimary, fontWeight: "700" }}>
        {status.playing ? "⏸ Tạm dừng" : "▶ Nghe lại trước khi lưu"}
      </Text>
    </TouchableOpacity>
  );
}
```

Render trong card: khi `pending` khác null thì thay nút ghi âm bằng khối preview:

```tsx
{pending ? (
  <>
    <PendingPreview uri={pending.uri} />
    <Field placeholder="Tiêu đề (tùy chọn)" value={draftTitle} onChangeText={setDraftTitle} />
    <Field placeholder="Tags, cách nhau dấu phẩy (tùy chọn)" value={draftTags} onChangeText={setDraftTags} />
    <View style={{ flexDirection: "row", gap: spacing.md }}>
      <TouchableOpacity style={[styles.recordBtn, { flex: 1 }]} onPress={save} disabled={busy}>
        <Text style={{ color: colors.onPrimary, fontWeight: "700" }}>
          {busy ? "Đang tải lên…" : "💾 Lưu"}
        </Text>
      </TouchableOpacity>
      <TouchableOpacity style={[styles.recordBtn, styles.recordBtnActive, { flex: 1 }]} onPress={discard} disabled={busy}>
        <Text style={{ color: colors.onPrimary, fontWeight: "700" }}>🗑 Hủy</Text>
      </TouchableOpacity>
    </View>
  </>
) : (
  <TouchableOpacity ...nút ghi âm hiện có... />
)}
```

(`Field` import từ `../../src/ui/form`; `formatDuration` import từ `../../src/util/format` — xóa bản local.)

Cleanup unmount (thay effect cleanup hiện có):

```tsx
useEffect(() => () => {
  if (savedTimer.current) clearTimeout(savedTimer.current);
  // Rời màn khi đang ghi: dừng recorder + trả audio mode, không giữ mic
  try { recorder.stop(); } catch {}
  setAudioModeAsync({ allowsRecording: false }).catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, []);
```

- [ ] **Step 4: Verify + Commit** — `npx tsc --noEmit`; smoke web: ghi → nghe lại → hủy; ghi → đặt title/tags → lưu.

```bash
git add frontend/src/api/voice.ts frontend/src/util/format.ts "frontend/app/(main)/today.tsx"
git commit -m "feat(fe): ghi am co nghe lai truoc khi luu, huy, tieu de + tags; khong mat audio khi upload loi"
```

---

### Task 19: FE thư viện ghi âm — title/duration/status, xóa, re-transcribe, seek, hết leak

**Files:**
- Modify: `frontend/app/(main)/voice-notes.tsx`
- Modify: `frontend/src/api/voice.ts` (`voiceNoteAudioSource` revoke blob cũ)

- [ ] **Step 1: voice.ts — chống leak blob web.** Module-level ref:

```ts
let _lastBlobUrl: string | null = null;

export async function voiceNoteAudioSource(id: string) {
  const url = `${API_URL}/api/v1/voice-notes/${id}/file`;
  const tokens = await getTokens();
  const headers = tokens?.access_token ? { Authorization: `Bearer ${tokens.access_token}` } : undefined;
  if (Platform.OS === "web") {
    // (giữ comment cũ về <audio> không nhận header)
    const resp = await fetch(url, { headers });
    if (!resp.ok) throw new Error(`Không tải được file ghi âm (${resp.status})`);
    const blob = await resp.blob();
    if (_lastBlobUrl) URL.revokeObjectURL(_lastBlobUrl); // blob cũ không revoke = leak
    _lastBlobUrl = URL.createObjectURL(blob);
    return { uri: _lastBlobUrl };
  }
  return { uri: url, headers };
}
```

- [ ] **Step 2: voice-notes.tsx** — nâng cấp row + player:

(a) `VoiceNoteRow` hiển thị `note.title` (fallback ngày giờ), duration, trạng thái transcript:

```tsx
import { formatDuration } from "../../src/util/format";

function transcriptLine(n: VoiceNote): string {
  if (n.transcript) return n.transcript;
  switch (n.transcript_status) {
    case "queued":
    case "processing":
      return "⏳ Đang xử lý transcript…";
    case "failed":
      return "⚠️ Nhận dạng thất bại — bấm 'Nhận dạng lại'";
    default:
      return "🔇 Chưa bật nhận dạng giọng nói — transcript sẽ có khi bật STT";
  }
}
```

Trong row:

```tsx
<Text style={{ fontWeight: "600", color: colors.text }}>
  {note.title || new Date(note.created_at).toLocaleString("vi-VN")}
</Text>
<Text style={styles.meta}>
  {new Date(note.created_at).toLocaleString("vi-VN")}
  {note.duration_seconds != null ? ` · ${formatDuration(note.duration_seconds * 1000)}` : ""}
</Text>
<Text style={{ color: note.transcript ? colors.text : colors.textMuted }}>
  {transcriptLine(note)}
</Text>
```

(b) Nút xóa 2-chạm + nút nhận dạng lại (props mới truyền từ screen):

```tsx
// state ở screen:
const [confirmingDeleteId, setConfirmingDeleteId] = useState<string | null>(null);

const remove = async (id: string) => {
  if (confirmingDeleteId !== id) {
    setConfirmingDeleteId(id); // chạm 1: hỏi; chạm 2 mới xóa
    return;
  }
  setConfirmingDeleteId(null);
  try {
    await deleteVoiceNote(id);
    if (playingId === id) setPlayingId(null);
    load();
  } catch (e: any) {
    setError(String(e?.message ?? e));
  }
};

const retranscribe = async (id: string) => {
  try {
    await retranscribeVoiceNote(id);
    load();
  } catch (e: any) {
    setError(
      String(e?.message ?? "").includes("stt_not_configured")
        ? "Chưa cấu hình dịch vụ nhận dạng giọng nói."
        : "Không gửi được yêu cầu nhận dạng lại.",
    );
  }
};
```

Trong row (dòng nút cuối):

```tsx
<View style={{ flexDirection: "row", gap: spacing.md }}>
  {note.transcript_status === "failed" && (
    <TouchableOpacity onPress={() => onRetranscribe(note.id)}>
      <Text style={{ color: colors.primary, fontWeight: "700" }}>↻ Nhận dạng lại</Text>
    </TouchableOpacity>
  )}
  <TouchableOpacity onPress={() => onDelete(note.id)}>
    <Text style={{ color: colors.danger, fontWeight: "700" }}>
      {confirmingDelete ? "Chạm lần nữa để xóa!" : "🗑 Xóa"}
    </Text>
  </TouchableOpacity>
</View>
```

(c) Progress + seek + tự reset khi phát xong (ở screen, dưới list — panel player đơn giản):

```tsx
useEffect(() => {
  if (status.didJustFinish) {
    setPlayingId(null);
    player.seekTo(0);
  }
}, [status.didJustFinish]); // eslint-disable-line react-hooks/exhaustive-deps
```

```tsx
{playingId && status.duration > 0 && (
  <View style={styles.playerBar}>
    <Text style={styles.meta}>
      {formatDuration(status.currentTime * 1000)} / {formatDuration(status.duration * 1000)}
    </Text>
    <View
      style={styles.progressTrack}
      onStartShouldSetResponder={() => true}
      onResponderRelease={(e) => {
        const { locationX } = e.nativeEvent;
        if (trackWidth.current > 0)
          player.seekTo((locationX / trackWidth.current) * status.duration);
      }}
      onLayout={(e) => { trackWidth.current = e.nativeEvent.layout.width; }}
    >
      <View style={[styles.progressFill,
        { width: `${(status.currentTime / status.duration) * 100}%` }]} />
    </View>
  </View>
)}
```

Với `const trackWidth = useRef(0);` và styles:

```ts
playerBar: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.md, gap: spacing.xs },
progressTrack: { height: 8, borderRadius: 4, backgroundColor: colors.divider, overflow: "hidden" },
progressFill: { height: 8, backgroundColor: colors.primary },
```

(d) `toggle` bọc try/catch: lỗi tải file (401/network) → `setError("Không phát được ghi âm — thử lại.")`.

- [ ] **Step 3: Verify + Commit** — `npx tsc --noEmit`; smoke web thư viện: phát/tạm dừng/seek/xóa.

```bash
git add frontend/src/api/voice.ts "frontend/app/(main)/voice-notes.tsx"
git commit -m "feat(fe): thu vien ghi am co title/duration/trang thai STT, xoa, nhan dang lai, seek + het leak blob"
```

---

### Task 20: Chốt — export OpenAPI, full test, typecheck

- [ ] **Step 1:** `cd backend && pytest tests/ -v` → toàn bộ PASS (fix nốt gì còn đỏ).
- [ ] **Step 2:** `cd frontend && npx tsc --noEmit` → sạch.
- [ ] **Step 3:** `cd backend && python scripts/export_openapi.py` (ghi `openapi.json` repo root — contract đổi: pending_action, voice fields/routes mới).
- [ ] **Step 4:** Commit:

```bash
git add openapi.json
git commit -m "chore: export openapi sau dot fix AI chat + voice"
```

- [ ] **Step 5:** Smoke test end-to-end bằng skill `verify` của repo (dựng postgres/redis + uvicorn + bắn request như FE) nếu môi trường cho phép.

---

## Self-Review đã chạy

- Coverage: 9 nhóm fix trong yêu cầu → Task 1-2 (timezone), 11 (confirm), 13 (markdown), 10 (queue_held + resume), 18 (voice preview/cancel/tags) + 17 (delete), 6-7-8 (queue isolation, history/instruction cap, caching), 9 + 5 (auto-title, max_tokens), 15-16 (transcribe async + status + re-transcribe + duration + size limit). Bonus từ review: Task 3 (cron bền), 4 (tin rỗng + TTL), 5 (tool lỗi), 12 (FE nuốt lỗi), 14 (tool chips + đang soạn), 19 (leak + seek).
- Type consistency: `_load_history(db, conversation_id, current_request_id)` dùng nhất quán Task 6-7; `uploadVoiceNote(uri, opts)` nhất quán Task 18; `VoiceNote.transcript_status` nhất quán Task 15/16/18/19; `VN_TZ` từ `app/tz.py` dùng ở Task 1-2.
- Known deviation: FE không có test runner → verification bằng typecheck + smoke; test BE cho Task 3/7/9 tái dùng fixture/helper của file test sẵn có (implementer đọc file đó trước khi viết).
