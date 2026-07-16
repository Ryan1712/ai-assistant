# Thiết kế FE (+ 1 sửa BE nhỏ) — Thảo luận/bình luận trong task

**Ngày:** 2026-07-16 · **Trạng thái:** Tự quyết theo yêu cầu user (không qua vòng hỏi xác nhận từng phần — xem [[feedback-minimize-confirmation-checkpoints]])

Lấp phần FE của tính năng "thảo luận trong task" — BE (`add_comment`/`list_comments`, REST `/api/v1/tasks/{id}/comments`) đã có từ trước nhưng chưa từng có UI. Không có tiền lệ hiển thị tên tác giả cho comment (chỉ có `author_id` thô) — thêm 1 field nhỏ vào response.

---

## 1. Phạm vi & Ranh giới

**Trong phạm vi:**
- 1 sửa BE nhỏ: `work_service.add_comment`/`list_comments` trả thêm `author_name` (resolve từ `User.full_name`) thay vì để FE tự xử lý UUID thô — theo đúng tiền lệ `audit_service`/Team screen.
- 1 API module FE (`src/api/comments.ts`).
- 1 section mới "Thảo luận" trong `tasks/[id].tsx`, thêm ngay sau `AttachmentsSection` đã có — cùng 1 màn hình, không phải route riêng.

**Ngoài phạm vi (YAGNI):**
- Không sửa/xóa comment (BE không có endpoint đó, giống tiền lệ Note/VoiceNote/Attachment).
- Không đính kèm file vào 1 comment cụ thể (đã quyết định khi thiết kế Attachment: đính kèm gắn vào Task nói chung).
- Không @mention, không reaction, không realtime (polling/websocket) — load 1 lần khi vào màn, thêm mới thì chèn ngay vào state cục bộ (giống cách `AttachmentsSection` đang làm khi upload xong).

---

## 2. Sửa BE — `backend/app/services/work_service.py` + `backend/app/schemas.py`

`CommentOut` (`backend/app/schemas.py:174-181`) thêm `author_name: str`:

```python
class CommentOut(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    author_id: uuid.UUID
    author_name: str
    content: str
    created_at: dt.datetime

    model_config = {"from_attributes": True}
```

`add_comment`/`list_comments` (`backend/app/services/work_service.py:192-206`) đổi từ trả ORM object sang trả dict có `author_name` (giống pattern `_out()` của `attachment_service`/`audit_service`) — KHÔNG đổi chữ ký hàm, KHÔNG đổi route:

```python
async def add_comment(db: AsyncSession, actor: User, task_id: uuid.UUID,
                      content: str) -> dict:
    task = await get_visible_task_or_404(db, actor, task_id)
    comment = TaskComment(workspace_id=actor.workspace_id, task_id=task.id,
                          author_id=actor.id, content=content)
    db.add(comment)
    await db.commit()
    return {"id": comment.id, "task_id": comment.task_id, "author_id": comment.author_id,
            "author_name": actor.full_name, "content": comment.content,
            "created_at": comment.created_at}


async def list_comments(db: AsyncSession, actor: User, task_id: uuid.UUID) -> list[dict]:
    task = await get_visible_task_or_404(db, actor, task_id)
    rows = (await db.execute(select(TaskComment).where(TaskComment.task_id == task.id)
                             .order_by(TaskComment.created_at.asc(), TaskComment.id.asc()))).scalars()
    comments = list(rows)
    author_ids = {c.author_id for c in comments}
    names: dict = {}
    if author_ids:
        users = (await db.execute(select(User).where(
            User.id.in_(author_ids), User.workspace_id == actor.workspace_id))).scalars()
        names = {u.id: u.full_name for u in users}
    return [{"id": c.id, "task_id": c.task_id, "author_id": c.author_id,
            "author_name": names.get(c.author_id, "?"), "content": c.content,
            "created_at": c.created_at} for c in comments]
```

Ghi chú: `add_comment` dùng thẳng `actor.full_name` (tác giả chính là actor, không cần query) — chỉ `list_comments` cần 1 query `User` gộp (giống `audit_service`, có lọc `workspace_id` theo đúng quy ước). Router `backend/app/api/tasks.py:79-89` không cần sửa gì — `response_model=CommentOut`/`list[CommentOut]` tự serialize dict có key khớp field.

---

## 3. API module FE — `frontend/src/api/comments.ts`

```ts
import { apiFetch } from "./client";

export type Comment = {
  id: string;
  task_id: string;
  author_id: string;
  author_name: string;
  content: string;
  created_at: string;
};

export const listComments = (taskId: string) =>
  apiFetch<Comment[]>(`/api/v1/tasks/${taskId}/comments`);

export const addComment = (taskId: string, content: string) =>
  apiFetch<Comment>(`/api/v1/tasks/${taskId}/comments`, {
    method: "POST",
    body: { content },
  });
```

---

## 4. Section "Thảo luận" trong `frontend/app/(main)/tasks/[id].tsx`

Thêm ngay sau `AttachmentsSection` (dòng 201 hiện tại), theo đúng cấu trúc card đã có (`styles.card`, `styles.cardTitle`, `styles.row`), tái dùng `Field`/`ErrorText` từ `src/ui/form.tsx`:

```tsx
function CommentRow({ c }: { c: Comment }) {
  return (
    <View style={styles.row}>
      <View style={{ flex: 1 }}>
        <Text style={{ fontWeight: "700" }}>{c.author_name}</Text>
        <Text style={type.body}>{c.content}</Text>
        <Text style={{ color: colors.textSecondary }}>
          {new Date(c.created_at).toLocaleString("vi-VN")}
        </Text>
      </View>
    </View>
  );
}

function CommentsSection({ taskId }: { taskId: string }) {
  const [comments, setComments] = useState<Comment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    listComments(taskId)
      .then(setComments)
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, [taskId]);

  const handleSend = async () => {
    const content = draft.trim();
    if (!content) return;
    setSending(true);
    setError(null);
    try {
      const created = await addComment(taskId, content);
      setComments((prev) => (prev ? [...prev, created] : [created]));
      setDraft("");
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setSending(false);
    }
  };

  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Thảo luận</Text>
      {comments === null && !error && <ActivityIndicator color={colors.primary} />}
      <ErrorText error={error} />
      {comments?.length === 0 && (
        <Text style={{ color: colors.textMuted }}>Chưa có bình luận nào</Text>
      )}
      {comments?.map((c) => (
        <CommentRow key={c.id} c={c} />
      ))}
      <Field placeholder="Viết bình luận..." value={draft} onChangeText={setDraft} multiline />
      <TouchableOpacity onPress={handleSend} disabled={sending || !draft.trim()}>
        {sending ? (
          <ActivityIndicator color={colors.primary} />
        ) : (
          <Text style={{ color: colors.primary, fontWeight: "700" }}>Gửi</Text>
        )}
      </TouchableOpacity>
    </View>
  );
}
```

Gắn vào màn chính — sau `<AttachmentsSection taskId={id} />`:

```tsx
          <AttachmentsSection taskId={id} />
          <CommentsSection taskId={id} />
```

Import thêm `Comment, addComment, listComments` từ `../../../src/api/comments`, và `Field` từ `../../../src/ui/form` (file này hiện chỉ import `ErrorText` từ đó, cần thêm `Field` vào cùng dòng import).

**Danh sách sắp xếp cũ→mới** (khác `AttachmentRow` mới→cũ) — khớp thứ tự BE trả về (`created_at.asc()`), giống hội thoại đọc từ trên xuống.

---

## 5. Xử lý lỗi & Testing

- Lỗi tải danh sách/gửi bình luận → `ErrorText` chung trong card (không phải `Alert` — đây là 1 phần dữ liệu của card, giống cách `AttachmentsSection` xử lý lỗi upload).
- Nút "Gửi" tắt khi đang gửi (`sending`) hoặc khi ô trống (`!draft.trim()`) — không validate gì thêm phía FE, để BE tự chịu trách nhiệm (task không thấy được → 404, hiện qua `ErrorText`).
- BE: `backend/tests/test_comments.py` đã có sẵn — thêm 1 test kiểm `author_name` xuất hiện đúng trong response `list_comments`/`add_comment` (không cần viết lại toàn bộ file, chỉ thêm test mới).
- FE: không có test framework — `npx tsc --noEmit` (0 lỗi) + chạy tay: mở task → thấy "Thảo luận" (rỗng nếu chưa có) → gõ + Gửi → thấy bình luận mới xuất hiện cuối danh sách với đúng tên mình → tải lại màn → thấy đúng cả 2 người (giống test BE `test_two_employees_same_task_can_discuss`) nếu test bằng 2 tài khoản.

---

## Self-review (đã chạy)

- **Placeholder scan:** không có TBD.
- **Nhất quán nội bộ:** `author_name` resolve theo đúng pattern đã dùng ở audit-log (`names.get(id, "?")` fallback, lọc `workspace_id`); `add_comment` tối ưu không query thừa vì actor chính là author.
- **Phạm vi:** nhỏ, 1 màn hình đã có sẵn cấu trúc để gắn thêm — ước lượng 2 task (BE schema/service change, FE section). Không cần tách plan riêng.
- **Ambiguity check:** đã chốt "gắn vào cùng `tasks/[id].tsx`, không phải route riêng", "sort cũ→mới", "không sửa/xóa comment" — không còn chỗ hiểu 2 nghĩa.
