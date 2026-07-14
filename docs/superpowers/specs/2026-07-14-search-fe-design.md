# Thiết kế — FE tìm kiếm xuyên suốt + task detail tối thiểu

**Ngày:** 2026-07-14 · **Trạng thái:** Đã duyệt qua brainstorming · **BE liên quan:** [2026-07-14-cross-search-design.md](2026-07-14-cross-search-design.md) (REST `GET /api/v1/search` đã xong, BE) · **Spec chức năng:** [funtional-plan.md](../../../funtional-plan.md) §8

Khép vòng tính năng tìm kiếm xuyên suốt: BE đã có `GET /api/v1/search?q=...` (trả `{tasks, notes, voice_notes, users, skills}`), nhưng FE chưa có màn nào gọi tới. Đây là spec cho phần FE — 1 tab tìm kiếm mới + 1 route chi tiết task tối thiểu (route chi tiết đầu tiên của app, vì hiện chưa có route `/tasks/[id]`/`/notes/[id]`/... nào cả).

---

## 1. Phạm vi & Ranh giới

**Trong phạm vi:**
- Tab thứ 4 "Tìm kiếm" (🔍) trong `app/(main)/_layout.tsx`.
- Màn `app/(main)/search.tsx`: ô nhập từ khóa + tìm khi bấm phím "search" trên bàn phím (không live-search/debounce) + hiển thị 5 nhóm kết quả (task/note/ghi âm/người/skill), đủ 4 trạng thái (loading/empty/error/success) theo `DESIGN.md`.
- Route ẩn `app/(main)/tasks/[id].tsx`: chi tiết task tối thiểu, chỉ đọc (title/status/percent/description/deadline/priority) — route detail *đầu tiên* của app.
- Dòng kết quả task trong màn search bấm được → điều hướng sang route trên. Note/ghi âm/người/skill chỉ hiển thị, không bấm được (giữ nguyên quy ước hiện có của `TaskLine` ở `today.tsx` — cũng không bấm được).
- 2 file API mới: `src/api/search.ts`, `src/api/tasks.ts`.

**Ngoài phạm vi (đẩy sau, YAGNI — không có yêu cầu rõ ràng):**
- Live-search/debounce khi gõ.
- Route chi tiết cho note/ghi âm/người/skill.
- Edit/comment/cập nhật tiến độ trên màn task detail — chỉ đọc.
- Danh sách assignee, lịch sử update/comment trên task detail.
- Phân trang/"xem thêm" kết quả tìm kiếm (BE giới hạn cứng 20/nhóm, không có cursor).

---

## 2. Điều hướng — route ẩn trong Tabs

Expo Router (SDK 57, xem `frontend/AGENTS.md`): thêm file `tasks/[id].tsx` dưới `app/(main)/` và khai báo trong `_layout.tsx`:

```tsx
<Tabs.Screen name="tasks/[id]" options={{ href: null }} />
```

`href: null` ẩn khỏi tab bar nhưng route vẫn điều hướng được qua `router.push(\`/tasks/${id}\`)`. Không tạo Stack lồng bên trong 1 tab (phức tạp không cần thiết) — route chi tiết vẫn nằm trong nhóm `(main)` nên vẫn được bọc bởi auth guard của `_layout.tsx` hiện có.

---

## 3. API layer

### `src/api/search.ts` (mới)

```ts
import { apiFetch } from "./client";

export type SearchTask = { id: string; title: string; status: string; project_id: string };
export type SearchNote = { id: string; content: string; note_date: string };
export type SearchVoiceNote = { id: string; transcript: string; created_at: string };
export type SearchUser = { id: string; full_name: string; email: string; role: string };
export type SearchSkill = { id: string; name: string; kind: string };

export type SearchResult = {
  tasks: SearchTask[];
  notes: SearchNote[];
  voice_notes: SearchVoiceNote[];
  users: SearchUser[];
  skills: SearchSkill[];
};

export const searchAll = (q: string) =>
  apiFetch<SearchResult>(`/api/v1/search?q=${encodeURIComponent(q)}`);
```

Field/type khớp chính xác `SearchOut`/`SearchTaskOut`/... ở `backend/app/schemas.py` (không thêm field không tồn tại ở BE).

### `src/api/tasks.ts` (mới — FE hiện chưa có file API nào cho task)

```ts
import { apiFetch } from "./client";

export type TaskDetail = {
  id: string;
  project_id: string;
  title: string;
  description: string;
  status: string;
  percent: number;
  deadline: string | null;
  priority: string;
  assignee_ids: string[];
};

export const getTask = (id: string) => apiFetch<TaskDetail>(`/api/v1/tasks/${id}`);
```

Khớp `TaskOut` ở `backend/app/schemas.py` — chỉ lấy field cần cho detail tối thiểu, `assignee_ids` giữ trong type để đúng shape response nhưng **không hiển thị** ở v1 (ngoài phạm vi).

---

## 4. Màn `app/(main)/search.tsx`

- State: `q` (input), `result: SearchResult | null` (chưa tìm lần nào = `null`), `loading: boolean`, `error: string | null`.
- `onSubmitEditing`: `setLoading(true); setError(null)` → gọi `searchAll(q)` → set `result` hoặc set `error` từ `ApiError`.
- 4 trạng thái:
  - **Loading:** `ActivityIndicator` (giống `today.tsx`).
  - **Empty (chưa tìm):** `result === null && !loading && !error` → caption `textMuted`: "Nhập từ khóa để tìm task, note, ghi âm, người, skill".
  - **Empty (tìm nhưng 0 kết quả):** `result !== null` và tổng 5 mảng rỗng → "Không tìm thấy kết quả nào cho “{q}”".
  - **Error:** `error && <ErrorText error={error} />` (component có sẵn ở `src/ui/form.tsx`) + có thể bấm lại nút tìm để thử lại (không cần nút "Thử lại" riêng — bàn phím search vẫn còn đó).
  - **Success:** 5 `Section`-style card, **ẩn hẳn card nào rỗng** (không hiện "Section trống" cho từng nhóm — khác với `today.tsx` vốn luôn hiện đủ card vì đó là dashboard cố định; ở đây tuỳ ngữ cảnh tìm kiếm nên bớt nhiễu).
- Render mỗi nhóm (dùng đúng token `theme.ts`, theo pattern `card`/`cardTitle` của `today.tsx`):
  - **Task** (🗂️): `TouchableOpacity` → `router.push(\`/tasks/${t.id}\`)`, hiện `title` + `status`.
  - **Note** (📝): `Text` — `content` (không cắt ngắn, theo spec BE không truncate).
  - **Ghi âm** (🎙️): `Text` — `transcript`.
  - **Người** (👤): `Text` — `full_name` + `email`.
  - **Skill** (🧠): `Text` — `name`.

---

## 5. Route `app/(main)/tasks/[id].tsx`

- Lấy `id` qua `useLocalSearchParams()`.
- `useEffect` gọi `getTask(id)` — 3 trạng thái (loading/error/success), không cần "empty" (task luôn có dữ liệu nếu fetch thành công; 404 rơi vào nhánh error).
- **Error:** bao gồm cả 404 — hiện `ErrorText` với thông điệp từ `ApiError` (BE trả `detail: "task_not_found"` khi không tìm thấy/khác quyền — hiện nguyên thông điệp đó qua `ErrorText`, không cần dịch riêng).
- **Success:** 1 card (`card`/`cardTitle` style) hiện:
  - `title` (`type.heading`)
  - `status` + `percent` (dòng phụ, giống `percent` style trong `today.tsx`)
  - `description` (nếu rỗng thì không hiện dòng, không hiện "chưa có mô tả")
  - `deadline` (format `toLocaleDateString("vi-VN")` nếu có, ẩn dòng nếu `null`)
  - `priority`
- Không có nút hành động nào (edit/comment/update) — thuần hiển thị.

---

## 6. Testing

FE hiện tại **không có test suite** (không tìm thấy Jest/RNTL config khi khảo sát) — nhất quán với các màn hình FE khác đã có (`today.tsx`, `chat.tsx` không có test đi kèm). Không thêm hạ tầng test mới trong phạm vi này; xác minh bằng chạy Expo dev server + thao tác tay (theo skill `run` nếu cần) thay vì unit test.

---

## Self-review (đã chạy)

- **Placeholder scan:** không có TBD; mọi quyết định (tab thứ 4, route ẩn `href: null`, task detail read-only tối thiểu, submit-to-search không debounce) đã chốt qua brainstorming.
- **Nhất quán nội bộ:** field/type ở `search.ts`/`tasks.ts` khớp chính xác response shape đã kiểm tra ở BE (`SearchOut`, `TaskOut`); dùng đúng component có sẵn (`Field`, `ErrorText`, token `theme.ts`) — không phát minh style/token mới, đúng `DESIGN.md`.
- **Phạm vi:** đủ nhỏ cho 1 implementation plan — ước lượng 3-4 task (API layer, search screen, task detail route + đăng ký tab, polish/manual verify). Không đụng BE (đã xong ở plan trước), không thêm migration/test framework mới.
- **Ambiguity check:** đã chốt rõ "note/voice/user/skill không bấm được", "ẩn card rỗng thay vì hiện empty-state riêng từng nhóm", "task detail không có hành động nào" — không còn chỗ hiểu 2 nghĩa.
