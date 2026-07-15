# Thiết kế — Đính kèm tài liệu trong task

**Ngày:** 2026-07-15 · **Trạng thái:** Đã duyệt qua brainstorming · **Spec chức năng:** [funtional-plan.md](../../../funtional-plan.md) §8 ("Thảo luận / bình luận trong task + đính kèm tài liệu")

Lấp phần "đính kèm tài liệu" của khoảng trống §8 — phần "thảo luận/bình luận" đã có sẵn (`TaskComment`, `add_comment`/`list_comments` trong `work_service.py`). Đây là 1 tính năng độc lập với comment, không mở rộng `TaskComment`.

---

## 1. Phạm vi & Ranh giới

**Trong phạm vi:**
- Model mới `Attachment` — file đính kèm gắn vào **1 task cụ thể** (`task_id` bắt buộc, khác `Note`/`VoiceNote` có `task_id` optional).
- Upload (multipart), liệt kê, tải xuống — tái dùng nguyên pattern lưu file của `voice_service.py` (UUID-named file trên đĩa, chống path traversal).
- Whitelist đuôi file + giới hạn dung lượng.
- REST 3 endpoint (`app/api/attachments.py`, router mới) + 1 tool chat read-only `list_task_attachments`.

**Ngoài phạm vi (cố ý, YAGNI):**
- **Xóa attachment** — không có endpoint xóa, giống tiền lệ `TaskComment`/`Note`/`VoiceNote` đều không có delete. Thêm sau nếu có yêu cầu rõ ràng.
- **Đính kèm vào Comment** (1 comment có file riêng) — đã quyết định trong brainstorming: attachment gắn vào Task nói chung, không sửa `TaskComment`.
- **Tool chat để upload** — không khả thi (LLM tool-calling không truyền binary), giống `VoiceNote` cũng không có tool upload. FE gọi REST trực tiếp qua file picker.
- **FE** — không nằm trong plan này, sẽ là 1 spec+plan riêng sau (theo quyết định brainstorming).
- **Đính kèm vào Project** (chỉ Note/VoiceNote hiện có `project_id` optional) — §8 chỉ nhắc "trong task", không mở rộng sang Project.
- **Virus scan / content-type sniffing sâu hơn whitelist đuôi file** — vượt quá nhu cầu hiện tại (workspace nội bộ, CEO/manager tự chịu trách nhiệm nội dung).

---

## 2. Model

Thêm vào `backend/app/models.py`, đặt cạnh `VoiceNote`:

```python
class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), index=True)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    file_path: Mapped[str] = mapped_column(String(512))
    original_filename: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
```

`original_filename` là điểm khác biệt có chủ đích so với `VoiceNote` (không lưu tên gốc, vì ghi âm chỉ cần nghe/đọc transcript) — với tài liệu, tên gốc (`"Hop_dong_A.pdf"`) là thông tin cần thiết để người dùng nhận diện file trong danh sách, còn `file_path` trên đĩa vẫn dùng UUID để tránh path traversal/trùng tên.

Migration mới: `alembic revision --autogenerate -m "attachments table"` — **học từ bugfix `12cce73`**: nếu autogenerate sinh cột Enum tái dùng type có sẵn (không áp dụng ở đây vì `Attachment` không có cột Enum, nhưng nếu sau này thêm thì nhớ `postgresql.ENUM(..., create_type=False)` chứ đừng `sa.Enum`).

---

## 3. Storage & Validation

`backend/app/services/attachment_service.py` (file mới), tái dùng gần như nguyên xi pattern của `voice_service.py`:

```python
_ALLOWED_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                 ".txt", ".png", ".jpg", ".jpeg", ".zip"}
_MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB


def _attachment_dir(workspace_id: uuid.UUID) -> Path:
    d = Path(get_settings().storage_dir) / "attachments" / str(workspace_id)
    d.mkdir(parents=True, exist_ok=True)
    return d
```

- Đuôi file không nằm trong whitelist → `422 unsupported_file_format`.
- `len(data) > _MAX_FILE_SIZE` → `422 file_too_large`.
- File lưu tại `{storage_dir}/attachments/{workspace_id}/{uuid}{ext}` — tên sinh bằng UUID, không dùng tên client gửi lên cho đường dẫn thật (giống `voice_service._voice_dir`), `original_filename` lưu riêng ở cột DB để hiển thị.

---

## 4. Service functions

```python
async def create_attachment(db: AsyncSession, actor: User, task_id: uuid.UUID, *,
                            filename: str, data: bytes) -> dict:
    ext = Path(filename or "").suffix.lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(422, "unsupported_file_format")
    if len(data) > _MAX_FILE_SIZE:
        raise HTTPException(422, "file_too_large")
    task = await get_visible_task_or_404(db, actor, task_id)

    file_path = _attachment_dir(actor.workspace_id) / f"{uuid.uuid4()}{ext}"
    file_path.write_bytes(data)
    attachment = Attachment(workspace_id=actor.workspace_id, task_id=task.id,
                            author_id=actor.id, file_path=str(file_path),
                            original_filename=filename or "file", file_size=len(data))
    db.add(attachment)
    await db.commit()
    return _out(attachment)


async def list_attachments(db: AsyncSession, actor: User, task_id: uuid.UUID) -> list[dict]:
    task = await get_visible_task_or_404(db, actor, task_id)
    rows = await db.execute(select(Attachment).where(Attachment.task_id == task.id)
                            .order_by(Attachment.created_at.desc()))
    return [_out(a) for a in rows.scalars()]


async def get_file_path(db: AsyncSession, actor: User, attachment_id: uuid.UUID) -> Path:
    attachment = await db.get(Attachment, attachment_id)
    if attachment is None or attachment.workspace_id != actor.workspace_id:
        raise HTTPException(404, "attachment_not_found")
    await get_visible_task_or_404(db, actor, attachment.task_id)  # 404 nếu không thấy task
    path = Path(attachment.file_path)
    if not path.is_file():
        raise HTTPException(404, "file_not_found")
    return path
```

Ghi chú thiết kế:
- **Permission = `get_visible_task_or_404`, y hệt `add_comment`/`list_comments`** — không viết logic quyền mới, đúng quyết định brainstorming ("ai thấy task thì upload/xem được").
- **`get_file_path` kiểm tra qua task, KHÁC `voice_service.get_file_path`** (vốn author-only) — vì attachment là tài liệu chung của task, không phải sở hữu cá nhân như ghi âm.
- **Thứ tự validate**: đuôi file + dung lượng kiểm tra TRƯỚC khi query task — tránh tốn 1 round-trip DB cho file rõ ràng sai định dạng/quá lớn (giống thứ tự trong `voice_service.create_voice_note`).

---

## 5. REST endpoints

`backend/app/api/attachments.py` (router mới, đăng ký trong `app/main.py` cạnh các router khác):

```python
router = APIRouter(prefix="/api/v1", tags=["attachments"])

@router.post("/tasks/{task_id}/attachments", status_code=201)
async def upload_attachment(task_id: uuid.UUID, file: UploadFile = File(...),
                            actor: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    data = await file.read()
    return await attachment_service.create_attachment(
        db, actor, task_id, filename=file.filename or "", data=data)


@router.get("/tasks/{task_id}/attachments")
async def list_attachments(task_id: uuid.UUID,
                           actor: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    return await attachment_service.list_attachments(db, actor, task_id)


@router.get("/attachments/{attachment_id}/file")
async def download_attachment(attachment_id: uuid.UUID,
                              actor: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    path = await attachment_service.get_file_path(db, actor, attachment_id)
    return FileResponse(path)
```

Response shape (`_out`, dùng cho cả upload/list): `{"id": str, "task_id": str, "author_id": str, "original_filename": str, "file_size": int, "created_at": datetime}`.

---

## 6. Tool chat

`backend/app/agent/tools.py`, đặt cạnh `list_voice_notes`/`get_voice_note`:

```python
class ListTaskAttachmentsToolIn(BaseModel):
    task_id: uuid.UUID


async def _list_task_attachments(db, actor, body: ListTaskAttachmentsToolIn) -> dict:
    attachments = await attachment_service.list_attachments(db, actor, body.task_id)
    return {"attachments": attachments}


_register("list_task_attachments", "Liệt kê tài liệu đính kèm của 1 task (tên file, dung "
          "lượng, người đính kèm, thời gian).", ListTaskAttachmentsToolIn,
          _list_task_attachments)
```

Không `sensitive` — chỉ đọc, không phải hành động nhạy cảm (giống `list_voice_notes`).

---

## 7. Xử lý lỗi

| Tình huống | Kết quả |
|---|---|
| Đuôi file không trong whitelist | `422 unsupported_file_format` |
| File > 20MB | `422 file_too_large` |
| Task không tồn tại/không thấy được (quyền) | `404 task_not_found` (từ `get_visible_task_or_404` có sẵn) |
| `attachment_id` không tồn tại/khác workspace | `404 attachment_not_found` |
| Attachment thuộc task actor không thấy được | `404 task_not_found` (từ `get_visible_task_or_404` trong `get_file_path`) |
| File vật lý bị mất trên đĩa (hiếm) | `404 file_not_found` |

---

## 8. Testing

TDD, test trước code sau, mỗi task 1 commit:

- `backend/tests/test_attachment_service.py`: upload thành công (đúng whitelist), sai đuôi file (422), quá dung lượng (422), task không thấy được → 404, list theo task, download qua task-visibility (không phải author-only — test 1 người KHÁC author nhưng thấy được task vẫn tải được), download attachment thuộc task không thấy được → 404, `attachment_id` khác workspace → 404.
- `backend/tests/test_attachments_api.py`: REST round-trip qua httpx (upload multipart thật), list, download trả đúng bytes, 404 cross-workspace.
- `backend/tests/test_agent_tools_attachments.py`: tool đăng ký, không sensitive, gọi qua `call_tool` trả đúng danh sách.
- Migration: `alembic revision --autogenerate -m "..."` rồi `alembic upgrade head` trên DB dev, xác nhận sạch (không lặp lại lỗi kiểu `12cce73`).
- Full pytest + `python scripts/export_openapi.py` (route mới → đổi contract).

---

## Self-review (đã chạy)

- **Placeholder scan:** không có TBD; whitelist đuôi file + giới hạn 20MB đã chốt cụ thể qua brainstorming (không để "phù hợp"/"hợp lý" mơ hồ).
- **Nhất quán nội bộ:** permission tái dùng đúng 1 hàm có sẵn (`get_visible_task_or_404`) xuyên suốt cả 3 service function, không có đường nào bỏ sót check quyền; `workspace_id` lọc ở cả `create_attachment` (qua task) và `get_file_path` (check trực tiếp trên `Attachment.workspace_id`).
- **Phạm vi:** đủ nhỏ cho 1 implementation plan — ước lượng 3 task (model+migration+service, REST, tool), giống cấu trúc offboarding/role-change. FE cố ý tách plan riêng.
- **Ambiguity check:** đã chốt rõ "gắn vào Task không phải Comment", "không có delete", "quyền = task-visibility không phải author-only", "không có tool upload" — không còn chỗ hiểu 2 nghĩa.
