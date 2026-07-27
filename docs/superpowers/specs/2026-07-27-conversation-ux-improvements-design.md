# Cải thiện UX hội thoại: tự đặt tên chat + thẻ bấm chọn khi AI hỏi lại

**Ngày:** 2026-07-27
**Trạng thái:** Đã duyệt hướng, chờ review spec → writing-plans

## 1. Bối cảnh

CEO phản ánh 2 điểm khó dùng, so với ChatGPT/Claude chat:

1. Tên cuộc trò chuyện hiện là 60 ký tự đầu của tin nhắn đầu tiên, cắt cứng — không phải tóm tắt, khó
   tìm lại trong danh sách.
2. Mỗi lần AI cần hỏi lại (phân biệt người/task trùng tên, xác nhận, chọn 1 trong vài lựa chọn...),
   CEO phải tự gõ câu trả lời — không có thẻ bấm chọn nhanh như ChatGPT/Claude.

Một tính năng thứ 3 (chỉ báo "AI đang xử lý") đã có sẵn code (`chat.tsx`, khối hiển thị
`runningTool`/`running`/`deep_running`/`queued`) nhưng CHƯA được CEO xác nhận qua test thực tế trên
Expo Go — **ngoài phạm vi spec này**, chỉ implement khi CEO xác nhận cần thêm gì sau khi test.

## 2. Tính năng A — Tự đặt tên cuộc trò chuyện bằng AI

### 2.1 Quyết định đã chốt (qua AskUserQuestion)
- Thời điểm tóm tắt: **sau khi AI trả lời xong tin nhắn đầu tiên** của cuộc trò chuyện (một lần duy
  nhất, không tóm tắt lại khi hội thoại phát triển thêm — giống hành vi ChatGPT).
- Cuộc trò chuyện cũ đã có sẵn: **đặt lại tên hết cho đồng bộ**, kể cả những cuộc từng bị đổi tên tay
  trước đây.
- Cơ chế chạy: **chạy ngầm dần dần sau khi deploy** (cron nền), không chặn luồng chat, không cần API
  đồng bộ riêng.

### 2.2 Data model
Thêm cột `title_locked: Mapped[bool]` (`default=False, server_default="false"`) vào `Conversation`
(`backend/app/models.py:362`). Migration mới nối vào head hiện tại, thêm cột với default `false` cho
TẤT CẢ bản ghi hiện có — không cần backfill logic riêng, vì default `false` tự động đưa mọi cuộc trò
chuyện cũ vào diện "chờ AI đặt tên", đúng ý "đặt lại tên hết".

Ý nghĩa cột: `title_locked = True` nghĩa là "tiêu đề này đã chốt, cron không được đụng vào nữa" — set
bởi (a) cron sau khi tự sinh tên, hoặc (b) người dùng tự đổi tên tay (PATCH). Không cần phân biệt
"do AI đặt" hay "do người dùng đặt" — một khi có tên thật (không phải fallback cắt chuỗi), coi như
xong.

### 2.3 Không đổi hành vi tạo tên tức thời
`send_message` (`backend/app/api/chat.py:166-169`) vẫn giữ nguyên: gán tạm `title = 60 ký tự đầu` ngay
khi tạo cuộc trò chuyện, để danh sách không trống trong lúc chờ cron chạy. `title_locked` mặc định
`False` nên tên tạm này vẫn nằm trong diện cron sẽ ghi đè.

### 2.4 Cron sinh tên
Hàm mới trong `backend/app/agent/worker.py`, đăng ký vào `WorkerSettings.cron_jobs` cùng lịch với các
cron khác hiện có (`second=0`, chạy mỗi phút):

- Điều kiện ứng viên: `title_locked = False` AND có ít nhất 1 `Message` role=assistant thuộc
  conversation đó (tức AI đã trả lời xong tin đầu).
- Giới hạn số lượng xử lý mỗi lượt chạy (vd 10 cuộc/lượt) để tránh dồn cục chi phí LLM ngay sau khi
  deploy — sweep toàn bộ lịch sử sẽ trải dần qua nhiều lượt cron, đúng ý "chạy ngầm dần dần".
- Với mỗi ứng viên: gọi `model_fast` (theo đúng pattern `classify_route`/`summarizer.py` đã dùng —
  `backend/app/config.py:22`) với vài tin nhắn đầu của cuộc trò chuyện, yêu cầu 1 câu tiêu đề ngắn
  (≤ ~50 ký tự, tiếng Việt, không dấu ngoặc kép bao quanh).
- Ghi `conv.title = <kết quả>` và `conv.title_locked = True` trong cùng 1 transaction. Lỗi gọi LLM
  (timeout, rate limit...) → bỏ qua ứng viên đó, KHÔNG set `title_locked`, để lượt cron sau thử lại
  (best-effort, giống tinh thần `embedding_service.index_content` không chặn luồng chính).

### 2.5 Endpoint đổi tên tay
`rename_conversation` (`backend/app/api/chat.py:121-126`) thêm `conv.title_locked = True` cùng với
`conv.title = body.title` — người dùng tự đổi tên thì cron không bao giờ ghi đè lại nữa.

## 3. Tính năng B — Thẻ bấm chọn khi AI hỏi lại (`suggest_replies`)

### 3.1 Phạm vi đã chốt
Áp dụng cho **mọi câu hỏi AI đặt ra nói chung** (không giới hạn riêng vụ phân biệt người/task trùng
tên) — model tự quyết định lúc nào đưa lựa chọn, dựa vào mô tả tool.

### 3.2 Tool mới
`backend/app/agent/tools.py` — đăng ký tool `suggest_replies`, theo đúng pattern các tool khác
(`_register(name, description, ToolIn, handler)`):

- Input schema: `SuggestRepliesToolIn { options: list[str] }`, ràng buộc 2–5 phần tử qua Pydantic
  (`Field(min_length=2, max_length=5)` ở cấp list, mỗi phần tử là chuỗi ngắn không rỗng).
- Handler: `async def _suggest_replies(db, actor, body) -> dict: return {"shown": True}` — không đụng
  DB, không side effect. Không phải sensitive tool (không vào `SENSITIVE_TOOLS`), không phải
  snapshot-write (không vào `SNAPSHOT_WRITE_TOOLS`).
- Thuộc nhóm `TOOL_GROUPS["core"]` (`backend/app/agent/tools.py:1033`) — dùng được ở mọi route, giống
  `propose_actions`/`resolve_person`.
- Mô tả tool (khớp best practice Anthropic: nêu rõ dùng-khi-nào + ràng buộc dữ liệu + khi-nào-KHÔNG-
  dùng, ví dụ cụ thể):

  > "Gọi tool này NGAY SAU KHI đã viết câu hỏi cho người dùng trong phần text, nếu câu hỏi có một tập
  > lựa chọn ngắn, rời rạc, rõ ràng (vd: chọn giữa 2 người trùng tên, xác nhận có/không, chọn 1 trong
  > vài mốc thời gian). Mỗi phần tử trong `options` PHẢI là nguyên văn câu trả lời ngắn gọn mà người
  > dùng sẽ gửi nếu chọn (vd: 'Nam Nguyễn', 'Có, tạo task mới'), KHÔNG phải nhãn mô tả. Tối đa 5 lựa
  > chọn. KHÔNG gọi tool này nếu câu hỏi mở, cần câu trả lời tự do không có sẵn đáp án ngắn."

### 3.3 Xử lý trong agent loop
`backend/app/agent/loop.py` — do `disable_parallel_tool_use=True` nên mỗi lượt tối đa 1 tool_use, và
`suggest_replies` không nằm trong `SENSITIVE_TOOLS` nên không khớp `first_gate` hiện có (dòng
454-456). Thêm 1 nhánh mới, đặt song song với nhánh `first_gate` (sau khi `first_gate` không khớp,
trước vòng lặp thực thi tool bình thường ở dòng 499):

- Nếu tool_use duy nhất trong lượt là `suggest_replies`: sinh NGAY 1 `tool_result` tổng hợp
  (`{"shown": true}`) gắn với đúng `tool_use_id`, lưu vào `Message` (role=user) — bắt buộc, vì hợp
  đồng API của Anthropic yêu cầu mọi `tool_use` phải có `tool_result` đi kèm ở lượt sau, nếu không lượt
  gọi tiếp theo của conversation sẽ lỗi 400 (bài học đã có từ orphaned tool_use trước đây).
  Sau đó **kết thúc lượt ngay** (giống nhánh `done.stop_reason != "tool_use"` ở dòng 434-449: set
  `req.status = done`, `finished_at`, `result_summary`, publish `request_done`, index embedding) —
  KHÔNG gọi lại LLM thêm lần nữa. Lý do: nếu để vòng lặp tiếp tục như tool thường (dòng 499-513), model
  sẽ bị gọi thêm 1 lượt ngay sau khi vừa hỏi xong — tốn API call vô ích và có thể khiến model nói lặp/
  thừa trong khi chỉ nên dừng lại chờ người dùng chọn.
- Không có bước "chờ xác nhận" như `propose_actions`/sensitive tool — `suggest_replies` không pause
  request, ô nhập text vẫn mở bình thường ngay sau đó, người dùng gõ tự do hay bấm thẻ đều được.

### 3.4 Frontend
`frontend/app/main/chat.tsx`:

- `Row` type (dòng 43-47): thêm biến thể `{ key: string; kind: "choices"; text: string; options: string[] }`
  (giữ `text` = câu hỏi AI vừa nói, để hiển thị cùng khối với các thẻ bên dưới).
- `messagesToRows` (dòng 145-165): khi duyệt `m.content`, nếu gặp `b.type === "tool_use" && b.name === "suggest_replies"`
  thì đẩy 1 row `kind: "choices"` với `options: b.input.options` thay vì rơi vào nhánh
  `labelForTool` chung (dòng 160-161) — không hiện dòng "Đã dùng suggest_replies" vô nghĩa với người
  dùng.
- `renderRow` (dòng 575+): thêm nhánh cho `kind === "choices"`, render các `TouchableOpacity` chip tái
  dùng style `onboardingChip`/`onboardingChipText` đã có (dòng 180, 722-733) — mỗi chip
  `onPress={() => submit(opt)}`, gọi thẳng hàm `submit` sẵn có (dòng 435) → gửi ngay nguyên văn lựa
  chọn làm tin nhắn mới, không có bước điền-trước-rồi-sửa.
- Thẻ hiển thị vĩnh viễn cùng với message đó khi cuộn lại lịch sử (không có trạng thái "đã dùng/vô
  hiệu hoá") — bấm lại một thẻ cũ chỉ đơn giản là gửi lại đúng text đó như một tin nhắn mới, không gây
  hại, không cần thêm state quản lý "đã chọn chưa".

## 4. Rủi ro & giới hạn đã biết

- **Tính năng B** phụ thuộc hoàn toàn vào việc model tuân theo mô tả tool để quyết định lúc nào gọi —
  không có ràng buộc cứng phía server. Có thể cần tinh chỉnh mô tả sau khi quan sát thực tế (giống các
  vòng sửa system prompt trước đây cho tool-name leakage).
- **Tính năng A**: nếu `model_fast` trả tên trùng lặp/nhàm chán cho nhiều cuộc hội thoại tương tự nhau
  (vd nhiều lần hỏi "giao task"), đây là giới hạn chất lượng model, không phải bug — không đặt mục
  tiêu giải quyết trong spec này.
- `title_locked` là cột nội bộ, KHÔNG thêm vào `ConversationOut` (schema response hiện liệt kê field
  tường minh, không tự động serialize cột mới) — không đổi API contract, không cần chạy lại
  `export_openapi.py` cho phần này.

## 5. Ngoài phạm vi

- Chỉ báo "AI đang xử lý" (Tính năng số 2 ban đầu CEO nêu) — chờ CEO test code hiện có qua Expo Go rồi
  quyết định có cần thêm gì không.
- Không đổi cơ chế `propose_actions`/sensitive-tool confirmation hiện có.
