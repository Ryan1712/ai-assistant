# Spec: Phase 6 (mảnh 1) — Onboarding

> Ngày: 2026-07-25
> Nguồn roadmap: `docs/superpowers/specs/2026-07-19-ai-intelligence-upgrade.md` §10.5
> Trạng thái tiền đề: Phase 0–5 đã xong (xem `PROJECT_CONTEXT.md`).

## 0. Bối cảnh & phạm vi

Phase 6 gốc (spec §10) gồm 5 mảnh khá độc lập: 10.1 analytics tools, 10.2 background
agents, 10.3 RAG prefetch + embeddings, 10.4 example bank, 10.5 onboarding. 10.2–10.4
phụ thuộc hạ tầng `embeddings`/pgvector chưa tồn tại (chưa cài, chưa chọn embedding
provider) — quá lớn cho 1 spec, tách riêng làm sau. Spec này chỉ làm **10.5
Onboarding**, cộng quyết định về **10.1**.

**10.1 (analytics tools) — không làm gì thêm.** 3/4 tool đã có từ Phase 2–3
(`get_project_health`, `get_progress_stats`, `get_directive_status`). Tool thứ 4
(`get_workload_summary`) **giữ nguyên quyết định cũ** (comment trong
`app/services/analytics_service.py`): không xây vì dữ liệu đã có sẵn trong workspace
snapshot (mục "Nhân sự & khối lượng", Phase 1) tiêm vào mọi system prompt — xây thêm
tool sẽ trùng lặp không ai dùng. Coi 10.1 là đã xong.

## 1. Phạm vi Onboarding

Áp dụng **chỉ cho CEO lúc tạo workspace mới** (không áp dụng cho manager/employee
kích hoạt qua `activate.tsx` sau này — họ vào 1 workspace đã có dữ liệu, không phải
"mới tinh", và các hành động gợi ý dưới đây đều là CEO-only theo `permissions.py`).

Bốn phần:
1. Seed message (scripted, 0 LLM).
2. 3 chip gợi ý (quick-reply), chỉ hiện 1 lần lúc mở màn.
3. Coach block (gợi ý ngắn cuối câu trả lời khi workspace còn thiếu setup).
4. Dán text danh sách công việc cũ → tự bóc thành `propose_actions` (khả năng
   chung, không gắn với chip, dùng được bất kỳ lúc nào).

**Không làm** (đã cân nhắc, loại khỏi phạm vi):
- Chip "Mời nhân viên" — tính năng `create_employee` vẫn hoạt động bình thường
  (CEO tạo tài khoản nhân viên/quản lý trực tiếp, trả `activation_code` — chỉ có
  luồng "nhân viên tự đăng ký bằng mã mời công ty" mới bị tắt 2026-07-23), nhưng
  người dùng quyết định không đưa vào bộ chip onboarding lần này.
- Chip nhập Excel/text riêng — khả năng #4 vẫn xây, nhưng không quảng cáo qua chip.
- Upload file `.xlsx` thật (parse bằng openpyxl) — chỉ hỗ trợ dán text.
- Onboarding cho manager/employee mới activate — ngoài phạm vi.

## 2. Seed message

**Cơ chế:** Hook thẳng vào `app/services/auth_service.py::signup_workspace()`. Ngay
sau khi tạo `Workspace` + `User(role=ceo)` (trong cùng transaction), tạo thêm:
- 1 `Conversation` (workspace_id, user_id=CEO vừa tạo) — đây sẽ là active
  conversation đầu tiên của CEO (nhất quán với bất biến "≤1 conversation sống"
  của Phase 5: workspace mới tinh nên chưa có conversation nào khác).
- 1 `Message` (conversation đó, `role=assistant`, `chat_request_id=None`,
  `is_seed=True`, content = câu chào viết sẵn — KHÔNG gọi LLM).

**Cột mới:** `Message.is_seed: bool` (default `False`), migration riêng. Mẫu hình
giống hệt `Message.is_ack` (Phase 4) — cờ đánh dấu nguồn gốc message, không phải
khái niệm mới. Khác `is_ack`: `is_seed` **không bị loại khỏi lịch sử gửi model**
(nó là ngữ cảnh hợp lệ — câu chào ngắn, không đứng giữa cặp tool_use/tool_result
nào, không có nguy cơ phá luật xen kẽ user/assistant).

**Nội dung câu chào** (tiếng Việt, ngắn gọn, không cứng nhắc — model KHÔNG sinh câu
này, nó là văn bản tĩnh viết sẵn trong code):
> "Chào anh! Tôi là trợ lý điều hành — nhắn cho tôi để giao việc, tạo project, hỏi
> tiến độ... Anh có thể bắt đầu bằng 1 trong các gợi ý dưới đây, hoặc gõ thẳng điều
> anh cần."

## 3. Quick-reply chips

**3 chip cuối cùng** (đã chốt qua thảo luận, thay cho bản nháp đầu có "Mời nhân
viên"):
- **"Tạo project"**
- **"Xem công việc"**
- **"Xem thử làm được gì"**

**Cơ chế:** Chip = câu gợi ý sẵn, bấm = gửi y hệt câu đó qua `submit()` (giống hệt
việc user tự gõ rồi bấm gửi) — KHÔNG có logic đặc biệt phía client/backend, model xử
lý bình thường theo luật hành xử 3 mức đã có (Phase 2: tường minh→làm ngay,
suy luận→propose_actions, nhạy cảm→confirm). "Tạo project" thiếu tên/mô tả cụ thể →
model tự hỏi lại đúng luật; "Xem công việc" → model gọi `list_tasks` (rỗng, trả note
"chưa có task nào" — vẫn là câu trả lời hợp lệ); "Xem thử làm được gì" → model tự mô
tả năng lực dựa system prompt.

**FE:** `MessageOut`/`Message` (FE type) thêm `is_seed: boolean`. Dải chip chỉ hiện
khi: đang ở LIVE mode (không phải history mode) VÀ `rows.length === 1` VÀ message đó
có `is_seed === true`. Sau khi có bất kỳ tin nhắn nào khác (kể cả do bấm chip), dải
chip biến mất vĩnh viễn khỏi màn hình (không tính lại — logic suy ra từ độ dài rows,
không cần state riêng lưu "đã ẩn chip chưa").

## 4. Coach block

**4 cờ** (tất cả scope theo `workspace_id`, tính lại mỗi lượt — KHÔNG cache, KHÔNG
lưu trạng thái "đã tốt nghiệp"; đủ 4 mốc thì tự động không còn cờ nào bật, khối tự
biến mất, không cần code riêng để "tắt hẳn"):
- `has_projects` — tái dùng `build_workspace_data()` (Phase 1, `snapshot_service.py`)
  đã trả `data["projects"]`: `len(...) > 0`. KHÔNG query thêm.
- `has_tasks` — cũng từ `build_workspace_data()`: bất kỳ project nào có
  `task_total > 0`. KHÔNG query thêm.
- `has_members` — từ `data["users"]`: `len(...) > 1` (CEO tự thân đã nằm trong danh
  sách này — cần >1 mới tính có mời thêm người). KHÔNG query thêm.
- `has_first_report` — **1 query mới, duy nhất phần thật sự mới**: `EXISTS(SELECT 1
  FROM reports WHERE workspace_id=...)`.

**Vị trí:** Hàm mới `get_coach_flags(db, workspace_id) -> dict` (đặt cạnh
`snapshot_service.py` hoặc file riêng nhỏ `onboarding_service.py` — quyết định ở
plan). Gọi trong `run_agent_loop` (`app/agent/loop.py`), CHỈ khi `actor.role ==
Role.ceo` (coach nudge vô nghĩa với manager/employee — họ không tạo được
project/mời người theo `permissions.py`). Còn cờ nào `False` → thêm 1 dòng vào
system prompt (block động, cạnh instructions/snapshot):

> "# Gợi ý dẫn dắt (chỉ hiện với CEO chưa hoàn tất thiết lập)
> Sau câu trả lời chính, thêm ĐÚNG 1 câu ngắn gợi ý bước tiếp theo hợp lý (tạo
> project / thêm task / mời nhân viên / xem báo cáo — tùy cờ nào chưa bật). Không
> lặp lại gợi ý y hệt câu trước nếu ngữ cảnh không đổi."

## 5. Dán text danh sách công việc cũ

**Không có gì mới về hạ tầng.** Chỉ thêm 1 đoạn vào system prompt TĨNH (luôn có, mọi
actor, không riêng CEO — vì đây là khả năng chung, giống propose_actions):

> "Khi người dùng dán 1 đoạn text dài liệt kê nhiều công việc (copy từ Excel/Word/
> ghi chú), tự nhận diện project + danh sách task + người phụ trách (nếu có nêu
> tên) từ nội dung đó, rồi gọi propose_actions MỘT LẦN gồm đủ create_project + N
> create_task + assign_task tương ứng — không hỏi lại từng dòng một, chỉ hỏi nếu
> tên người nhắc tới bị nhập nhằng (resolve_person)."

`propose_actions` đã hỗ trợ `actions: list[...]` không giới hạn số lượng
(`min_length=1`, không có max) — không cần đổi schema.

## 6. Việc cần làm (tổng hợp cho plan)

**Backend:**
- Migration: `messages.is_seed` (boolean, default false).
- `models.py`: `Message.is_seed`.
- `auth_service.py::signup_workspace`: tạo `Conversation` + seed `Message` trong
  cùng transaction.
- `get_coach_flags(db, workspace_id) -> dict` (hàm mới, tái dùng
  `build_workspace_data`).
- `loop.py::run_agent_loop`: gọi `get_coach_flags` khi `actor.role == ceo`, thêm
  block coach vào `dynamic_parts` nếu còn cờ `False`.
- `_build_system_prompt` (hoặc block tĩnh tương đương): thêm đoạn hướng dẫn dán-text
  ở mục 5.
- `schemas.py`: `MessageOut.is_seed: bool`.
- Export lại `openapi.json`.

**Frontend:**
- `src/api/chat.ts`: `Message.is_seed: boolean`.
- `app/main/chat.tsx`: hiện dải 3 chip khi `rows.length===1 && rows[0].is_seed &&
  !historyMode`; bấm chip = gọi `submit()` với text chip.

**Test:**
- `signup_workspace` tạo đúng Conversation + Message(is_seed=True, chat_request_id
  is None, content = câu chào cố định).
- `get_coach_flags`: đúng/sai từng cờ theo dữ liệu (project/task/member/report có
  hay không); coach block xuất hiện/biến mất đúng trong system prompt của
  `run_agent_loop`; KHÔNG xuất hiện khi actor là manager/employee.
- Regression: `run_agent_loop`/`signup_workspace` test cũ không đổi hành vi ngoài
  phần mới.
- FE: `tsc --noEmit` (không có test suite tự động).

## 7. Không làm (YAGNI / ngoài phạm vi)

- 10.2/10.3/10.4 (background agents, RAG/embeddings, example bank) → mảnh Phase 6
  riêng, sau khi hạ tầng embeddings được thiết kế.
- `get_workload_summary` → giữ quyết định cũ, không xây.
- Chip/luồng riêng cho import file `.xlsx` thật.
- Onboarding cho manager/employee.
- Lưu trạng thái "đã tốt nghiệp coach" — tính lại mỗi lượt là đủ rẻ, không cần cache.
