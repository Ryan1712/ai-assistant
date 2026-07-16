# Thảo luận/bình luận trong task (FE) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Task detail screen hiển thị được thảo luận (danh sách bình luận + gửi bình luận mới), tái dùng REST đã có sẵn từ trước.

**Architecture:** 1 sửa BE nhỏ (`CommentOut` thêm `author_name`, `work_service.add_comment`/`list_comments` trả dict resolve tên thay vì ORM object). FE: 1 API module (`src/api/comments.ts`) + 1 section mới gắn vào `tasks/[id].tsx` đã có sẵn (không route riêng).

**Tech Stack:** FastAPI/Pydantic/SQLAlchemy (BE), Expo SDK 57 + React Native `StyleSheet` (FE). Không thêm dependency.

**Spec thiết kế:** [docs/superpowers/specs/2026-07-16-task-comments-fe-design.md](../specs/2026-07-16-task-comments-fe-design.md)

## Global Constraints

- Không sửa/xóa comment — chỉ thêm mới + liệt kê, giống tiền lệ Note/VoiceNote/Attachment.
- `author_name` resolve BE-side, lọc `workspace_id` khi query `User` (theo quy ước mọi bảng đều lọc workspace).
- `add_comment` dùng thẳng `actor.full_name` — KHÔNG query `User` thêm (actor chính là author).
- Section "Thảo luận" gắn vào CÙNG `tasks/[id].tsx`, KHÔNG tạo route mới.
- Danh sách sắp xếp cũ→mới (khớp thứ tự BE `created_at.asc()`).
- FE không có test suite — `npx tsc --noEmit` (0 lỗi) là xác minh duy nhất. BE dùng TDD (pytest).
- Đổi API contract (BE) → chạy lại `python scripts/export_openapi.py`.

---

### Task 1: BE — `CommentOut` thêm `author_name`

**Files:**
- Modify: `backend/app/schemas.py:174-181` (`CommentOut`)
- Modify: `backend/app/services/work_service.py:192-206` (`add_comment`, `list_comments`)
- Test: `backend/tests/test_comments.py` (thêm test mới vào file đã có)

**Interfaces:**
- Produces: `CommentOut` có thêm `author_name: str`. `work_service.add_comment(db, actor, task_id, content) -> dict`, `work_service.list_comments(db, actor, task_id) -> list[dict]` — chữ ký hàm KHÔNG đổi, chỉ đổi kiểu trả về (dict thay vì ORM object) và có thêm key `author_name`. Task 2 (FE) dùng field này qua REST, không gọi trực tiếp service.

- [ ] **Step 1: Viết test thất bại trong `backend/tests/test_comments.py`**

Thêm vào cuối file (giữ nguyên `_h`, `_task_with_two_employees` và 2 test đã có):

```python
@pytest.mark.asyncio
async def test_comment_includes_author_name(client):
    ceo_h, e1, e2, tid = await _task_with_two_employees(client)
    r = await client.post(f"/api/v1/tasks/{tid}/comments", headers=_h(e1),
                          json={"content": "xin chao"})
    assert r.status_code == 201, r.text
    assert r.json()["author_name"] == "e1@a.vn"

    lst = await client.get(f"/api/v1/tasks/{tid}/comments", headers=_h(e2))
    assert lst.json()[0]["author_name"] == "e1@a.vn"
```

Lưu ý: `_invite_and_join` (trong `tests/conftest.py`) tạo `full_name=email` cho mỗi người dùng (xem `join = await client.post("/api/v1/auth/signup-invite", json={..., "full_name": email, ...})`) — nên `full_name` của `e1@a.vn` chính là chuỗi `"e1@a.vn"`, assert trên đúng với dữ liệu seed thật, không phải giả định.

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `cd backend && pytest tests/test_comments.py -v`
Expected: FAIL — `KeyError: 'author_name'` (field chưa tồn tại trong response).

- [ ] **Step 3: Sửa `CommentOut` trong `backend/app/schemas.py`**

Thay khối `class CommentOut` (dòng 174-181 hiện tại) bằng:

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

- [ ] **Step 4: Sửa `add_comment`/`list_comments` trong `backend/app/services/work_service.py`**

Thay 2 hàm (dòng 192-206 hiện tại) bằng:

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

`User` đã có sẵn trong import của `work_service.py` (dòng 8 hiện tại: `from app.models import Notification, Project, Task, TaskAssignee, TaskComment, TaskUpdate, User`) — không cần sửa import.

- [ ] **Step 5: Chạy test, xác nhận PASS**

Run: `cd backend && pytest tests/test_comments.py -v`
Expected: PASS — 3/3 tests xanh (2 test cũ + 1 test mới).

- [ ] **Step 6: Chạy toàn bộ test suite**

Run: `cd backend && pytest tests/ -v`
Expected: PASS toàn bộ.

- [ ] **Step 7: Xuất lại OpenAPI contract cho FE**

Run: `cd backend && python scripts/export_openapi.py`
Expected: `openapi.json` cập nhật, `CommentOut` schema có thêm `author_name`.

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas.py backend/app/services/work_service.py backend/tests/test_comments.py openapi.json
git commit -m "feat(be): CommentOut them author_name cho FE thao luan"
```

---

### Task 2: FE — API module + section "Thảo luận" trong `tasks/[id].tsx`

**Files:**
- Create: `frontend/src/api/comments.ts`
- Modify: `frontend/app/(main)/tasks/[id].tsx`

**Interfaces:**
- Consumes: `apiFetch` (đã có), `Field`/`ErrorText` từ `frontend/src/ui/form.tsx` (đã có).
- Produces: `type Comment`, `listComments(taskId)`, `addComment(taskId, content)` — dùng nội bộ trong `tasks/[id].tsx`, không có task nào khác tiêu thụ.

- [ ] **Step 1: Tạo `frontend/src/api/comments.ts`**

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

- [ ] **Step 2: Xác minh bằng typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: không có output (0 lỗi).

- [ ] **Step 3: Commit riêng file API module**

```bash
git add frontend/src/api/comments.ts
git commit -m "feat(fe): api layer thao luan (list/add comment)"
```

- [ ] **Step 4: Sửa import đầu `frontend/app/(main)/tasks/[id].tsx`**

Sửa dòng import `ErrorText` hiện tại (dòng 24):

```tsx
import { ErrorText, Field } from "../../../src/ui/form";
```

Thêm 1 dòng import mới ngay sau khối import `attachments` (dòng 23 hiện tại):

```tsx
import { Comment, addComment, listComments } from "../../../src/api/comments";
```

- [ ] **Step 5: Thêm `CommentRow`/`CommentsSection` — chèn ngay trước `export default function TaskDetailScreen()` (dòng 157 hiện tại)**

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

- [ ] **Step 6: Gắn `<CommentsSection>` vào màn chính**

Sửa khối JSX chính (dòng 201 hiện tại) — thêm 1 dòng ngay sau `<AttachmentsSection taskId={id} />`:

```tsx
          <AttachmentsSection taskId={id} />
          <CommentsSection taskId={id} />
```

- [ ] **Step 7: Xác minh bằng typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: không có output (0 lỗi).

- [ ] **Step 8: Commit**

```bash
git add frontend/app/\(main\)/tasks/\[id\].tsx
git commit -m "feat(fe): section thao luan trong man chi tiet task"
```

---

## Ghi chú

- Không có test tự động cho Task 2 (FE chưa có hạ tầng test) — `npx tsc --noEmit` là bước xác minh duy nhất bắt buộc agent chạy. Xác minh bằng mắt qua Expo dev server nên làm thủ công sau khi cả 2 task xong: mở 1 task → thấy "Thảo luận" (rỗng nếu chưa có) → gõ + Gửi → thấy bình luận mới cuối danh sách với đúng tên mình.
- Không sửa/xóa comment, không đính kèm file vào comment — cố ý theo spec §1, không thêm trong plan này.
