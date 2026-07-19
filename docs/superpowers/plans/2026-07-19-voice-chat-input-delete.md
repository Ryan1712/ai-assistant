# Voice input chat + đính kèm audio + xóa task/project — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chat nhận input bằng giọng nói (iOS dictation cho lệnh ngắn, đính kèm file audio cho meeting dài) + xóa được task/project (spec `docs/superpowers/specs/2026-07-19-voice-chat-input-delete-design.md`).

**Architecture:** BE giữ router→service→model; đính kèm audio đi qua voice-notes endpoint sẵn có rồi gắn `voice_note_id` vào ChatRequest/Message (1 migration); bước transcribe-trước-agent nằm trong worker, chỉ chạy khi `stt_mock=False`. FE: dictation cô lập trong 1 component riêng có guard require để không vỡ Expo Go/web thiếu API.

**Tech Stack:** FastAPI + SQLAlchemy 2 async + arq (BE); Expo 57 / RN 0.86, dependency FE mới: `expo-speech-recognition`.

## Global Constraints

- Commit message tiếng Việt không dấu ở subject; kết thúc bằng `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`; mỗi task một commit.
- TDD backend: test trước, code sau. FE verify bằng `npx tsc --noEmit` (trong `frontend/`).
- Backend test: `cd backend` + venv `.venv\Scripts\activate` → `pytest tests/<file> -v`.
- KHÔNG dùng PowerShell `Get-Content | Set-Content` với file tiếng Việt — dùng Edit/Write tool.
- Alembic head hiện tại: `f0a1b2c3d4e5` (migration mới nối vào đây).
- Mọi query lọc `workspace_id`; quyền check ở service layer; xóa task/project **chỉ CEO** (`require_ceo`).
- Locale dictation hardcode `vi-VN`. Nút mic/đính kèm phải ẨN (không phải disable) khi môi trường không hỗ trợ.
- Đổi contract (schemas/routes/tools) → task cuối chạy `python scripts/export_openapi.py`.
- Branch: `feature/voice-chat-input` tạo từ `main` sau khi commit plan này.

---

## Task 1: BE — voice_note_id trên ChatRequest/Message + send_message nhận đính kèm

**Files:**
- Modify: `backend/app/models.py` (class `ChatRequest` ~dòng 328, class `Message` ~dòng 346)
- Create: `backend/alembic/versions/a1b2c3d4e5f6_chat_voice_attachment.py`
- Modify: `backend/app/schemas.py` (`MessageSendIn` ~326, `ChatRequestOut` ~340, `MessageOut` ~352)
- Modify: `backend/app/api/chat.py` (`send_message` ~76)
- Test: `backend/tests/test_chat_voice_attachment.py` (mới)

**Interfaces:**
- Produces: `ChatRequest.voice_note_id`, `Message.voice_note_id` (nullable FK `voice_notes.id`, ondelete SET NULL); `MessageSendIn.voice_note_id: uuid | None`; `MessageOut.voice_note_id`, `ChatRequestOut.voice_note_id`. Task 2 và Task 4 dùng các field này.

- [ ] **Step 1: Viết test fail** — dựng client + fake arq pool theo đúng fixture `chat_client` trong `backend/tests/test_chat_api.py` (đọc file đó, tái dùng cách dựng); upload voice note bằng helper `_upload_files()`/`_h()` theo pattern `backend/tests/test_voice_notes.py`:

```python
# backend/tests/test_chat_voice_attachment.py
import io
import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.chat import get_arq_pool
from app.db import get_db
from app.main import create_app
from tests.conftest import _ceo_headers, _invite_and_join


class _FakeArqPool:
    async def enqueue_job(self, name, *args, **kwargs):
        return "job"


@pytest.fixture
async def client(engine, storage_dir):
    app = create_app()
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_arq_pool] = lambda: _FakeArqPool()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _audio_files():
    return {"file": ("a.m4a", io.BytesIO(b"fake"), "audio/m4a")}


@pytest.mark.asyncio
async def test_gui_tin_kem_ghi_am(client):
    h = await _ceo_headers(client)
    vid = (await client.post("/api/v1/voice-notes", headers=h, files=_audio_files())).json()["id"]
    conv = (await client.post("/api/v1/conversations", headers=h, json={})).json()

    r = await client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=h,
                          json={"content": "bóc task từ cuộc họp này", "voice_note_id": vid})
    assert r.status_code == 201
    assert r.json()["voice_note_id"] == vid

    msgs = (await client.get(f"/api/v1/conversations/{conv['id']}/messages", headers=h)).json()
    assert msgs[0]["voice_note_id"] == vid
    text = msgs[0]["content"][0]["text"]
    assert "bóc task từ cuộc họp này" in text
    assert "[Đính kèm ghi âm" in text  # model phải biết có file


@pytest.mark.asyncio
async def test_ghi_am_cua_nguoi_khac_404(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    m1_h = {"Authorization": f"Bearer {m1['access_token']}"}
    vid = (await client.post("/api/v1/voice-notes", headers=m1_h, files=_audio_files())).json()["id"]
    conv = (await client.post("/api/v1/conversations", headers=ceo_h, json={})).json()

    r = await client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=ceo_h,
                          json={"content": "x", "voice_note_id": vid})
    assert r.status_code == 404  # voice note author-only, CEO cũng không mượn được


@pytest.mark.asyncio
async def test_khong_kem_ghi_am_van_nhu_cu(client):
    h = await _ceo_headers(client)
    conv = (await client.post("/api/v1/conversations", headers=h, json={})).json()
    r = await client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=h,
                          json={"content": "tin thuong"})
    assert r.status_code == 201
    assert r.json()["voice_note_id"] is None
```

- [ ] **Step 2: Chạy fail** — `pytest tests/test_chat_voice_attachment.py -v` → FAIL (voice_note_id không tồn tại).

- [ ] **Step 3: Implement**

`models.py` — thêm vào `ChatRequest` (cạnh các cột hiện có) và `Message` (sau `chat_request_id`):

```python
    # Đính kèm ghi âm làm input cho AI (spec 2026-07-19): file dài user ném vào
    # chat; transcript (khi có STT) sẽ được append vào Message.content ở worker.
    voice_note_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("voice_notes.id", ondelete="SET NULL"), nullable=True)
```

Migration `a1b2c3d4e5f6_chat_voice_attachment.py` (down_revision = `"f0a1b2c3d4e5"`):

```python
"""chat: dinh kem voice note lam input"""
import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_requests", sa.Column(
        "voice_note_id", sa.Uuid(), sa.ForeignKey("voice_notes.id", ondelete="SET NULL"),
        nullable=True))
    op.add_column("messages", sa.Column(
        "voice_note_id", sa.Uuid(), sa.ForeignKey("voice_notes.id", ondelete="SET NULL"),
        nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "voice_note_id")
    op.drop_column("chat_requests", "voice_note_id")
```

`schemas.py`:

```python
class MessageSendIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    voice_note_id: uuid.UUID | None = None
    # (giữ nguyên field_validator _strip_not_blank hiện có)
```

`ChatRequestOut` thêm `voice_note_id: uuid.UUID | None = None`; `MessageOut` thêm `voice_note_id: uuid.UUID | None = None`.

`chat.py::send_message` — sau `_get_owned_conversation_or_404`, trước tạo `req`:

```python
    note_line = ""
    if body.voice_note_id is not None:
        # get_voice_note raise 404 nếu không phải chủ ghi âm / khác workspace —
        # danh tính từ JWT, không tin client.
        note = await voice_service.get_voice_note(db, actor, body.voice_note_id)
        label = note["title"] or (f"{note['duration_seconds']:.0f}s" if note["duration_seconds"] else "audio")
        note_line = f"\n[Đính kèm ghi âm: {label} — transcript sẽ được nối vào nếu đã nhận dạng]"
```

`req = ChatRequest(..., voice_note_id=body.voice_note_id)`; Message content: `[{"type": "text", "text": body.content + note_line}]`. Import `voice_service` từ `app.services`.

- [ ] **Step 4: Chạy pass** — `pytest tests/test_chat_voice_attachment.py tests/test_chat_api.py -v` → PASS. Chạy `alembic upgrade head` trên DB dev (docker 5435) xác nhận migration sạch.

- [ ] **Step 5: Commit** — `git add backend/ && git commit -m "feat(be): gui tin nhan chat kem ghi am (voice_note_id tren request/message)"`

---

## Task 2: BE — worker transcribe trước khi chạy agent (khi có STT thật)

**Files:**
- Modify: `backend/app/services/voice_service.py` (thêm hàm cuối file)
- Modify: `backend/app/agent/worker.py` (`process_conversation` ~dòng 55, ngay trước `run_agent_loop`)
- Test: thêm vào `backend/tests/test_chat_voice_attachment.py`

**Interfaces:**
- Consumes: `ChatRequest.voice_note_id` (Task 1), `transcribe_note(db, voice_note_id)` sẵn có.
- Produces: `voice_service.inject_transcript_for_request(db, req) -> None` — worker gọi trước `run_agent_loop`.

- [ ] **Step 1: Viết test fail**

```python
# thêm vào test_chat_voice_attachment.py
from sqlalchemy import select

from app.models import ChatRequest, Message, MessageRole, VoiceNote
from app.services import voice_service


class _FakeSTT:
    async def transcribe(self, data: bytes, filename: str):
        return "noi dung cuoc hop: giao viec cho Nam", "vi"


@pytest.mark.asyncio
async def test_inject_transcript_khi_stt_that(client, db_session, monkeypatch):
    monkeypatch.setattr("app.config.get_settings().__class__.stt_mock", False, raising=False)
    monkeypatch.setattr(voice_service, "get_transcription_client", lambda: _FakeSTT())

    h = await _ceo_headers(client)
    vid = (await client.post("/api/v1/voice-notes", headers=h, files=_audio_files())).json()["id"]
    conv = (await client.post("/api/v1/conversations", headers=h, json={})).json()
    await client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=h,
                      json={"content": "tom tat cuoc hop", "voice_note_id": vid})

    req = (await db_session.execute(select(ChatRequest).where(
        ChatRequest.conversation_id == uuid.UUID(conv["id"])))).scalar_one()
    await voice_service.inject_transcript_for_request(db_session, req)

    msg = (await db_session.execute(select(Message).where(
        Message.chat_request_id == req.id, Message.role == MessageRole.user))).scalar_one()
    joined = "\n".join(b["text"] for b in msg.content if b.get("type") == "text")
    assert "noi dung cuoc hop: giao viec cho Nam" in joined
    # Gọi lần 2 phải idempotent — không nối transcript 2 lần
    await voice_service.inject_transcript_for_request(db_session, req)
    await db_session.refresh(msg)
    assert msg.content[-1]["text"].count("noi dung cuoc hop") == 1


@pytest.mark.asyncio
async def test_inject_bo_qua_khi_stt_mock(client, db_session):
    h = await _ceo_headers(client)
    vid = (await client.post("/api/v1/voice-notes", headers=h, files=_audio_files())).json()["id"]
    conv = (await client.post("/api/v1/conversations", headers=h, json={})).json()
    await client.post(f"/api/v1/conversations/{conv['id']}/messages", headers=h,
                      json={"content": "x", "voice_note_id": vid})
    req = (await db_session.execute(select(ChatRequest).where(
        ChatRequest.conversation_id == uuid.UUID(conv["id"])))).scalar_one()
    await voice_service.inject_transcript_for_request(db_session, req)  # không raise, không đổi gì
    msg = (await db_session.execute(select(Message).where(
        Message.chat_request_id == req.id))).scalar_one()
    assert "[Transcript ghi âm]" not in "".join(b["text"] for b in msg.content)
```

Lưu ý monkeypatch settings: `get_settings()` là lru_cache — cách chắc chắn hơn là `monkeypatch.setattr(voice_service, "get_settings", lambda: SimpleNamespace(stt_mock=False, storage_dir=...))`. Implementer đọc cách các test hiện có trong `test_voice_notes.py` fake settings (fixture `storage_dir`) và làm cùng kiểu — miễn là test xanh và không rò rỉ sang test khác.

- [ ] **Step 2: Chạy fail.**

- [ ] **Step 3: Implement** — cuối `voice_service.py`:

```python
_TRANSCRIPT_MARK = "[Transcript ghi âm]"


async def inject_transcript_for_request(db: AsyncSession, req) -> None:
    """Trước khi agent chạy 1 request có đính kèm ghi âm: transcribe (nếu STT thật
    được bật và chưa done) rồi nối transcript vào user Message của request — nhờ đó
    MỌI lượt sau của conversation đều thấy nội dung qua _load_history, không cần
    cơ chế nhớ riêng. stt_mock=True thì bỏ qua (AI chỉ thấy dòng '[Đính kèm ghi âm...]')."""
    if req.voice_note_id is None or get_settings().stt_mock:
        return
    note = await db.get(VoiceNote, req.voice_note_id)
    if note is None:
        return
    if note.transcript_status != "done":
        await transcribe_note(db, note.id)
        await db.refresh(note)
    if note.transcript_status != "done" or not note.transcript:
        return
    from app.models import Message, MessageRole  # tránh import vòng ở đầu file nếu có
    msg = (await db.execute(select(Message).where(
        Message.chat_request_id == req.id, Message.role == MessageRole.user,
    ))).scalars().first()
    if msg is None:
        return
    if any(b.get("type") == "text" and _TRANSCRIPT_MARK in b.get("text", "")
           for b in msg.content):
        return  # idempotent — worker retry không nối trùng
    msg.content = msg.content + [
        {"type": "text", "text": f"{_TRANSCRIPT_MARK}:\n{note.transcript}"}]
    await db.commit()
```

(JSON column: gán list MỚI như trên thì SQLAlchemy mới thấy thay đổi — đừng `.append` tại chỗ.)

`worker.py::process_conversation` — ngay trước `await run_agent_loop(...)`:

```python
            if req.voice_note_id is not None:
                await voice_service.inject_transcript_for_request(db, req)
            await run_agent_loop(db, req, llm, publisher, is_cancelled=is_cancelled)
```

- [ ] **Step 4: Chạy pass** — `pytest tests/test_chat_voice_attachment.py -v`.

- [ ] **Step 5: Commit** — `git commit -m "feat(be): worker noi transcript ghi am vao message truoc khi agent chay (cho STT that)"`

---

## Task 3: BE — xóa task/project (service + REST + tool nhạy cảm)

**Files:**
- Modify: `backend/app/services/work_service.py` (thêm 2 hàm sau `update_task`)
- Modify: `backend/app/api/tasks.py` (+route DELETE), `backend/app/api/projects.py` (+route DELETE)
- Modify: `backend/app/agent/tools.py` (2 tool mới + thêm vào `SENSITIVE_TOOLS` ~dòng 708)
- Test: `backend/tests/test_delete_task_project.py` (mới)

**Interfaces:**
- Produces: `work_service.delete_task(db, actor, task_id) -> None`, `work_service.delete_project(db, actor, project_id) -> None`; `DELETE /api/v1/tasks/{id}` 204; `DELETE /api/v1/projects/{id}` 204; tools `delete_task`/`delete_project` (sensitive).

- [ ] **Step 1: Viết test fail** — dựng dữ liệu qua REST như pattern `test_tasks.py` hiện có (đọc trước, tái dùng helper):

```python
# backend/tests/test_delete_task_project.py — khung chính (implementer tái dùng
# fixture/client pattern của tests/test_tasks.py, các case bắt buộc:)

# 1. CEO xóa task -> 204; GET task đó -> 404; assignees/updates/comments/attachments
#    row con bị xóa (query trực tiếp db_session đếm = 0); file attachment trên đĩa
#    biến mất (unlink); voice_note/email có task_id đó -> task_id thành None.
# 2. Manager/employee xóa task -> 403.
# 3. CEO workspace A xóa task workspace B -> 404.
# 4. CEO xóa project có 2 task -> 204; cả 2 task + row con biến mất; GET project 404.
# 5. Tool: "delete_task" và "delete_project" nằm trong SENSITIVE_TOOLS; len(TOOLS)
#    tăng đúng 2 so với hiện tại (grep test len(TOOLS) hiện có để bump các assertion cũ).
```

Viết test thật đầy đủ cho cả 5 nhóm — mỗi nhóm ít nhất 1 test function, assert bằng truy vấn DB thật (`db_session`), không mock service.

- [ ] **Step 2: Chạy fail.**

- [ ] **Step 3: Implement** — `work_service.py`:

```python
async def delete_task(db: AsyncSession, actor: User, task_id: uuid.UUID) -> None:
    require_ceo(actor)
    task = await db.get(Task, task_id)
    if task is None or task.workspace_id != actor.workspace_id:
        raise HTTPException(404, "task_not_found")
    await _delete_task_rows(db, task)
    await db.commit()


async def _delete_task_rows(db: AsyncSession, task) -> None:
    """Xóa 1 task + mọi row con. KHÔNG commit — caller gom transaction."""
    from app.models import Attachment, Email, TaskAssignee, TaskComment, TaskUpdate, VoiceNote
    atts = (await db.execute(select(Attachment).where(
        Attachment.task_id == task.id))).scalars().all()
    for att in atts:
        try:
            Path(att.file_path).unlink(missing_ok=True)  # file mất/hỏng không chặn xóa
        except OSError:
            pass
        await db.delete(att)
    for model in (TaskAssignee, TaskUpdate, TaskComment):
        await db.execute(sa_delete(model).where(model.task_id == task.id))
    # Tham chiếu lỏng (cột nullable) -> gỡ link, giữ nguyên dữ liệu gốc
    await db.execute(sa_update(VoiceNote).where(VoiceNote.task_id == task.id)
                     .values(task_id=None))
    await db.execute(sa_update(Email).where(Email.task_id == task.id).values(task_id=None))
    await db.delete(task)


async def delete_project(db: AsyncSession, actor: User, project_id: uuid.UUID) -> None:
    require_ceo(actor)
    project = await db.get(Project, project_id)
    if project is None or project.workspace_id != actor.workspace_id:
        raise HTTPException(404, "project_not_found")
    tasks = (await db.execute(select(Task).where(Task.project_id == project_id))).scalars().all()
    for task in tasks:
        await _delete_task_rows(db, task)
    from app.models import Email, VoiceNote
    await db.execute(sa_update(VoiceNote).where(VoiceNote.project_id == project_id)
                     .values(project_id=None))
    await db.execute(sa_update(Email).where(Email.project_id == project_id)
                     .values(project_id=None))
    await db.delete(project)
    await db.commit()
```

(Import đầu file: `from pathlib import Path`, `from sqlalchemy import delete as sa_delete, update as sa_update` — implementer kiểm tra tên model Email có cột `task_id`/`project_id` trong `models.py` trước, nếu tên khác thì chỉnh theo thực tế.)

Routes:

```python
# tasks.py
@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: uuid.UUID, actor: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    await work_service.delete_task(db, actor, task_id)


# projects.py
@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: uuid.UUID, actor: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    await work_service.delete_project(db, actor, project_id)
```

Tools (`tools.py`, cạnh update_task/update_project; input model chỉ có `task_id`/`project_id`):

```python
class DeleteTaskToolIn(BaseModel):
    task_id: uuid.UUID


class DeleteProjectToolIn(BaseModel):
    project_id: uuid.UUID


async def _delete_task(db, actor, body):
    await work_service.delete_task(db, actor, body.task_id)
    return {"deleted": True}


async def _delete_project(db, actor, body):
    await work_service.delete_project(db, actor, body.project_id)
    return {"deleted": True}


_register("delete_task", "Xóa vĩnh viễn 1 task (chỉ CEO; xóa cả bình luận/cập nhật/"
          "đính kèm của nó).", DeleteTaskToolIn, _delete_task)
_register("delete_project", "Xóa vĩnh viễn 1 project VÀ TOÀN BỘ task bên trong "
          "(chỉ CEO).", DeleteProjectToolIn, _delete_project)
```

Thêm `"delete_task", "delete_project"` vào `SENSITIVE_TOOLS`. Bump mọi assertion `len(TOOLS) == N` trong tests (+2) — grep `len(TOOLS)`.

- [ ] **Step 4: Chạy pass** — `pytest tests/test_delete_task_project.py tests/ -v` (full suite).

- [ ] **Step 5: Commit** — `git commit -m "feat(be): xoa task/project (CEO-only, cascade, tool nhay cam qua confirm card)"`

---

## Task 4: FE — đính kèm audio vào chat + bubble audio

**Files:**
- Modify: `frontend/src/api/chat.ts` (`sendMessage`, type `Message`, `ChatRequest`)
- Modify: `frontend/app/(main)/chat.tsx`

**Interfaces:**
- Consumes: `uploadVoiceNote(uri, opts)` (voice.ts sẵn có), `voiceNoteAudioSource(id)` (voice.ts sẵn có), BE Task 1.
- Produces: `sendMessage(conversationId, content, voiceNoteId?)`; `Message.voice_note_id`; Row kind `"user"` có `voiceNoteId?`.

- [ ] **Step 1: chat.ts**

```ts
export type Message = {
  id: string;
  role: "user" | "assistant";
  content: ContentBlock[];
  voice_note_id: string | null;
  created_at: string;
};
// ChatRequest thêm: voice_note_id: string | null;

export const sendMessage = (conversationId: string, content: string, voiceNoteId?: string) =>
  apiFetch<ChatRequest>(`/api/v1/conversations/${conversationId}/messages`, {
    method: "POST",
    body: voiceNoteId ? { content, voice_note_id: voiceNoteId } : { content },
  });
```

- [ ] **Step 2: chat.tsx — chọn file + gửi.** Import `* as DocumentPicker from "expo-document-picker"`, `uploadVoiceNote`, `voiceNoteAudioSource` từ `../../src/api/voice`, `useAudioPlayer, useAudioPlayerStatus` từ `expo-audio`. State mới:

```ts
const [attachedAudio, setAttachedAudio] = useState<{ uri: string; name: string } | null>(null);
const [audioPlayingId, setAudioPlayingId] = useState<string | null>(null);
const audioPlayer = useAudioPlayer(null);
const audioStatus = useAudioPlayerStatus(audioPlayer);
```

Nút 📎 cạnh ô nhập (trong `styles.inputBar`, trước TextInput):

```tsx
<TouchableOpacity
  style={styles.attachBtn}
  onPress={async () => {
    const res = await DocumentPicker.getDocumentAsync({ type: "audio/*", copyToCacheDirectory: true });
    if (!res.canceled && res.assets?.[0]) {
      setAttachedAudio({ uri: res.assets[0].uri, name: res.assets[0].name });
    }
  }}
  accessibilityLabel="Đính kèm file ghi âm"
>
  <Text style={{ fontSize: 20 }}>📎</Text>
</TouchableOpacity>
```

Chip hiển thị trên inputBar khi `attachedAudio` khác null (tên file + nút ✕ bỏ đính kèm).

`submit` sửa: nếu có `attachedAudio` → cho phép content rỗng (mặc định `"Xử lý file ghi âm này giúp tôi"`), upload trước rồi gửi kèm id; lỗi upload → giữ nguyên attachment + báo lỗi:

```ts
const submit = async () => {
  if (!conversationId) return;
  const content = input.trim() || (attachedAudio ? "Xử lý file ghi âm này giúp tôi" : "");
  if (!content) return;
  setInput("");
  try {
    let voiceNoteId: string | undefined;
    if (attachedAudio) {
      const note = await uploadVoiceNote(attachedAudio.uri, {});
      voiceNoteId = note.id;
    }
    const req = await sendMessage(conversationId, content, voiceNoteId);
    contentByRequest.current.set(req.id, content);
    setAttachedAudio(null);
    if (held && isResumePhrase(content)) setHeld(false);
    setRows((prev) => [...prev, { key: `u-${req.id}`, kind: "user", text: content,
                                  voiceNoteId: voiceNoteId ?? null }]);
    await refreshQueue(conversationId);
  } catch (e: any) {
    setInput(content); // giữ chữ + giữ attachment khi lỗi
    setRows((prev) => [...prev, { key: `senderr-${Date.now()}`, kind: "system",
      text: `⚠️ Gửi thất bại (${String(e?.message ?? e).slice(0, 80)}) — nội dung đã được giữ lại.` }]);
  }
};
```

- [ ] **Step 3: Row + render bubble audio.** Row kind `"user"`/`"assistant"` thêm `voiceNoteId?: string | null`. `loadHistory` map `voiceNoteId: m.voice_note_id`. Trong renderItem, với row user có voiceNoteId:

```tsx
{item.kind === "user" && item.voiceNoteId && (
  <TouchableOpacity
    onPress={async () => {
      try {
        if (audioPlayingId === item.voiceNoteId) {
          audioStatus.playing ? audioPlayer.pause() : audioPlayer.play();
          return;
        }
        const source = await voiceNoteAudioSource(item.voiceNoteId!);
        audioPlayer.replace(source);
        audioPlayer.play();
        setAudioPlayingId(item.voiceNoteId!);
      } catch {}
    }}
    style={{ marginTop: spacing.xs }}
  >
    <Text style={{ color: colors.onPrimary, fontWeight: "700" }}>
      {audioPlayingId === item.voiceNoteId && audioStatus.playing ? "⏸ Ghi âm đính kèm" : "▶ Ghi âm đính kèm"}
    </Text>
  </TouchableOpacity>
)}
```

Style mới: `attachBtn: { paddingHorizontal: spacing.sm, paddingVertical: spacing.sm }`, `attachChip: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceAlt, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.xs }`.

- [ ] **Step 4: Verify + Commit** — `npx tsc --noEmit` sạch. `git commit -m "feat(fe): dinh kem file ghi am vao chat lam input cho AI + bubble audio phat lai"`

---

## Task 5: FE — mic dictation trong chat (iOS SFSpeechRecognizer + Web Speech API)

**Files:**
- Modify: `frontend/package.json` (dependency `expo-speech-recognition`)
- Modify: `frontend/app.json` (config plugin + permission strings)
- Create: `frontend/src/voice/DictationButton.tsx`
- Modify: `frontend/app/(main)/chat.tsx` (render nút cạnh ô nhập)

**Interfaces:**
- Produces: `<DictationButton onText={(text) => ...} />` — component tự ẩn khi môi trường không hỗ trợ; `onText` nhận transcript tăng dần (interim + final).

- [ ] **Step 1: Cài + config** — `cd frontend && npx expo install expo-speech-recognition`. Thêm vào `app.json > expo > plugins` (giữ nguyên plugin sẵn có):

```json
[
  "expo-speech-recognition",
  {
    "microphonePermission": "Cho phép dùng micro để nói với trợ lý AI",
    "speechRecognitionPermission": "Chuyển giọng nói của bạn thành văn bản để gửi cho trợ lý AI"
  }
]
```

- [ ] **Step 2: DictationButton.tsx** — guard require để Expo Go/web-không-hỗ-trợ KHÔNG crash (pattern giống guard push notification). Implementer PHẢI đối chiếu API thật trong `node_modules/expo-speech-recognition` (README + `.d.ts`) trước khi viết — khung dự kiến:

```tsx
import React, { useEffect, useRef, useState } from "react";
import { Text, TouchableOpacity } from "react-native";
import { colors, spacing } from "../ui/theme";

// Native module — thiếu (Expo Go) hoặc web không có SpeechRecognition thì null
let Speech: typeof import("expo-speech-recognition") | null = null;
try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  Speech = require("expo-speech-recognition");
} catch {}

export function DictationButton({ onText }: { onText: (text: string) => void }) {
  const [available, setAvailable] = useState(false);
  const [listening, setListening] = useState(false);
  const subs = useRef<{ remove: () => void }[]>([]);

  useEffect(() => {
    if (!Speech) return;
    try {
      setAvailable(Speech.ExpoSpeechRecognitionModule.isRecognitionAvailable());
    } catch {}
    return () => subs.current.forEach((s) => s.remove());
  }, []);

  if (!available) return null;

  const stop = () => {
    Speech!.ExpoSpeechRecognitionModule.stop();
    setListening(false);
  };

  const start = async () => {
    const perm = await Speech!.ExpoSpeechRecognitionModule.requestPermissionsAsync();
    if (!perm.granted) return;
    subs.current.push(
      Speech!.addSpeechRecognitionListener("result", (e: any) => {
        const t = e.results?.[0]?.transcript;
        if (t) onText(t);
      }),
      Speech!.addSpeechRecognitionListener("end", () => setListening(false)),
      Speech!.addSpeechRecognitionListener("error", () => setListening(false)),
    );
    Speech!.ExpoSpeechRecognitionModule.start({ lang: "vi-VN", interimResults: true });
    setListening(true);
  };

  return (
    <TouchableOpacity
      onPress={listening ? stop : start}
      style={{ paddingHorizontal: spacing.sm, paddingVertical: spacing.sm }}
      accessibilityLabel={listening ? "Dừng nói" : "Nói với trợ lý"}
    >
      <Text style={{ fontSize: 20 }}>{listening ? "🔴" : "🎙️"}</Text>
    </TouchableOpacity>
  );
}
```

- [ ] **Step 3: Gắn vào chat.tsx** — trong `styles.inputBar`, cạnh nút 📎:

```tsx
<DictationButton onText={(t) => setInput(t)} />
```

(`onText` nhận transcript TÍCH LŨY của phiên nói hiện tại → `setInput(t)` thay toàn bộ — người dùng muốn giữ text cũ thì dừng nói rồi gõ thêm; giữ đơn giản v1.)

- [ ] **Step 4: Verify + Commit** — `npx tsc --noEmit` sạch; web Chrome: nút mic hiện, bấm nói thử (Web Speech API); môi trường không hỗ trợ: nút tự ẩn (kiểm tra bằng cách tạm sửa `available=false`). `git commit -m "feat(fe): noi voi tro ly AI bang giong (iOS dictation, an khi moi truong khong ho tro)"`

---

## Task 6: FE — nút xóa task ở task detail

**Files:**
- Modify: `frontend/src/api/tasks.ts` (hoặc file api tương ứng — grep `tasks/[id]` để tìm; thêm `deleteTask`)
- Modify: `frontend/app/(main)/tasks/[id].tsx`

**Interfaces:**
- Consumes: `DELETE /api/v1/tasks/{id}` (Task 3).
- Produces: `deleteTask(id: string): Promise<void>`.

- [ ] **Step 1: api** — `export const deleteTask = (id: string) => apiFetch<void>(`/api/v1/tasks/${id}`, { method: "DELETE" });`

- [ ] **Step 2: UI** — cuối màn task detail thêm nút "🗑 Xóa task" 2-chạm xác nhận (pattern y hệt thư viện ghi âm: chạm 1 đổi text "Chạm lần nữa để xóa!", chạm 2 gọi `deleteTask` → `router.back()`; lỗi (403 với non-CEO) → hiện message thô qua ErrorText — KHÔNG tự check role ở FE, theo pattern Team screen).

- [ ] **Step 3: Verify + Commit** — `npx tsc --noEmit`. `git commit -m "feat(fe): nut xoa task trong man chi tiet (2 cham xac nhan)"`

---

## Task 7: Chốt — export OpenAPI, full test, typecheck, smoke

- [ ] **Step 1:** `cd backend && pytest tests/ -v` → PASS toàn bộ.
- [ ] **Step 2:** `cd frontend && npx tsc --noEmit` → sạch.
- [ ] **Step 3:** `cd backend && python scripts/export_openapi.py` → commit `openapi.json` (`git commit -m "chore: export openapi (voice attachment + delete task/project)"`).
- [ ] **Step 4:** Smoke Playwright trên web (backend local 8010 + expo web): gửi tin kèm file audio (dùng `setInputFiles` cho document picker nếu khả thi, không thì gọi API trực tiếp rồi reload chat xác nhận bubble audio hiện + phát được); xóa task qua chat với confirm card; nút mic hiện trên Chrome.

---

## Self-Review đã chạy

- Coverage: spec Feature 1 → Task 5; Feature 2 → Task 1, 2, 4; Feature 3 → Task 3, 6; contract → Task 7.
- Type consistency: `voice_note_id` xuyên suốt Task 1→2→4; `sendMessage(conversationId, content, voiceNoteId?)` Task 4; `inject_transcript_for_request(db, req)` Task 2 = tên worker gọi.
- Known risks ghi rõ trong task: API `expo-speech-recognition` phải đối chiếu `.d.ts` thật (Task 5 Step 2); tên cột Email kiểm tra trước khi viết cascade (Task 3 Step 3); monkeypatch settings theo pattern test sẵn có (Task 2 Step 1).
