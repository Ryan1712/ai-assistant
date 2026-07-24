# Spec: Phase 5 — Session model (một luồng duy nhất)

> Ngày: 2026-07-24
> Nguồn roadmap: `docs/superpowers/specs/2026-07-19-ai-intelligence-upgrade.md` §9
> Trạng thái tiền đề: Phase 0–4 đã xong (xem `PROJECT_CONTEXT.md` mục 13).

## 0. Mục tiêu & bối cảnh

Mô hình nhiều-chat (kiểu ChatGPT) tồn tại vì ở đó chat = bộ nhớ. Kiến trúc này đã
chuyển bộ nhớ ra snapshot (Phase 1) + directive (Phase 3) → chat chỉ là nơi **ra
lệnh**, không phải nơi lưu trữ. Vậy KHÔNG bắt user quản lý nhiều chat. UX đích =
"nhắn cho trợ lý" một luồng liên tục kiểu Zalo.

Hai vấn đề kỹ thuật phải giải để một-luồng khả thi:
1. **Context window**: hội thoại dài (200+ message) sẽ vượt cửa sổ context → mọi
   tin sau đó fail vĩnh viễn. Cần **nén** phần cũ.
2. **Vệ sinh phiên**: một conversation kéo dài vô hạn (row DB phình, ranh giới
   "sang ngày mới" mờ). Cần **xoay** conversation ngầm mà user không phải bấm.

## 1. Phạm vi

**Trong Phase 5:**
- Rolling summary (nén message cũ trong 1 conversation).
- Xoay conversation ngầm server-side (idle > 12h HOẶC > 150 message sống).
- Timeline xuyên conversation (FE render một luồng liền mạch).
- Bỏ nút "New chat" khỏi UX chính (giữ route ẩn xem lịch sử).

**Đẩy sang Phase 6 (KHÔNG làm ở Phase 5):**
- Ký ức xuyên session bằng embeddings/pgvector (spec gốc §10.3). Lý do: chưa có
  hạ tầng nào (không bảng `embeddings`, không indexer), pgvector không chạy trên
  SQLite của test suite, và trùng hẳn Phase 6. Acceptance *"hôm qua tôi dặn gì?"*
  vẫn đạt nhờ `rolling_summary` được **mang sang** khi xoay conversation — nội
  dung cũ sống trong summary của active conversation, không cần retrieval vector.

## 2. Thay đổi data model

`Conversation` thêm 3 cột (1 migration `session_model_rolling_summary`):

| Cột | Kiểu | Ý nghĩa |
|---|---|---|
| `rolling_summary` | `Text`, default `""` | Bản nén các message cũ đã rời cửa sổ verbatim. Tiêm vào SYSTEM prompt, KHÔNG phải message. |
| `summary_through_at` | `DateTime(tz)` nullable | Mốc ranh giới: message `created_at <= mốc` đã gộp vào summary; message sau mốc gửi nguyên văn. NULL = chưa nén gì. |
| `archived_at` | `DateTime(tz)` nullable | NULL = đang sống (active-able); set khi bị xoay ra. |

Toàn bộ là text/datetime → chạy được cả Postgres (prod/dev) lẫn SQLite (test).

## 3. Rolling summary — nén trong 1 conversation

Hằng số module (`app/agent/loop.py` hoặc service riêng, dễ chỉnh):
- `SUMMARY_TRIGGER = 60` — số message **sống** (sau `summary_through_at`, đã lọc
  `is_ack`/rỗng/queued) vượt ngưỡng này thì nén.
- `SUMMARY_KEEP_RECENT = 40` — số message đuôi giữ nguyên văn (không nén).

**Cơ chế nén** (`maybe_compress_history(db, conv, llm)`):
- Chạy trong `process_conversation` **trước** khi dispatch router/loop (dùng
  `model_fast` = `llm` fast client). Đặt ở đây để phủ CẢ fast path lẫn deep path
  (deep job đọc conv sau, thấy summary đã cập nhật).
- Đếm message sống sau mốc. Nếu > `SUMMARY_TRIGGER`:
  1. Lấy phần cần gộp = mọi message sống từ mốc tới `(count - SUMMARY_KEEP_RECENT)`.
  2. **Đẩy điểm cắt tới message user-text an toàn tiếp theo** (không cắt giữa cặp
     `tool_use`/`tool_result` — tái dùng đúng guard trong `_load_history` hiện tại).
     Phần trước điểm cắt gộp vào summary; điểm cắt trở đi giữ verbatim.
  3. Gọi `model_fast` KHÔNG tool: prompt = summary hiện có + đoạn cần gộp, yêu cầu
     giữ lại quyết định / con số / tên người-task-deadline / việc chưa xong. Output
     → `rolling_summary` mới.
  4. `summary_through_at = created_at của message cuối trong phần đã gộp`.

**`_load_history` đổi**:
- Thêm tham số `since: datetime | None` = `conv.summary_through_at`. Chỉ nạp message
  `created_at > since` (cạnh các filter cũ: skip queued/cancelled-chưa-chạy, lọc
  `is_ack`, bỏ content rỗng). Giữ nguyên cap `MAX_HISTORY_MESSAGES=80` + guard
  không mở đầu bằng `tool_result` mồ côi.

**Tiêm summary vào SYSTEM prompt** (KHÔNG chèn làm message):
- Trong `run_agent_loop`: fetch `conv`, nếu `conv.rolling_summary` không rỗng thì
  `dynamic_parts.append("# Tóm tắt hội thoại trước đó\n" + conv.rolling_summary)`
  — đặt CUỐI khối động (gần message nhất), đúng §11 "Tóm tắt hội thoại trước".
- Lý do KHÔNG làm message: chèn 1 message giữa lịch sử phá luật user/assistant xen
  kẽ bắt buộc của Anthropic (đúng bài học `is_ack` ở Phase 4). Summary là context
  nền, thuộc system prompt.
- Deep path tự hưởng vì injection nằm trong `run_agent_loop` dùng chung.

## 4. Xoay conversation ngầm — server-side

**Bất biến**: mỗi user có ≤1 conversation "sống" (`archived_at IS NULL`, mới nhất).
Với dữ liệu cũ (nhiều conversation cold-start đều `archived_at=NULL`), "active" =
cái mới nhất; các cái cũ vẫn hiện trong timeline/history nhưng không được chọn làm
active. Từ đây trở đi, mỗi lần xoay archive cái cũ trước khi tạo cái mới → đúng một
luồng sống.

**`get_or_rotate_active_conversation(db, actor, now=None) -> Conversation`**
(`now` inject được để test idle):
1. Tìm conv sống (`archived_at IS NULL`, `order by created_at desc`). Không có →
   tạo mới, trả về.
2. Điều kiện xoay conv sống hiện tại:
   - **idle**: `now - last_activity > 12h`, với `last_activity = max(Message.created_at)`
     trong conv, fallback `conv.created_at`.
   - **HOẶC size**: số message sống > `ROTATE_MAX_MESSAGES = 150`.
3. **Không xoay nếu còn việc dang dở**: có request `queued`/`running`/`deep_running`/
   `awaiting_confirmation`, hoặc `queue_held=True` → hoãn (trả về conv hiện tại),
   tránh bỏ rơi queue giữa chừng.
4. Nếu cần xoay & rảnh việc:
   - Nén **toàn bộ** đuôi còn lại vào `rolling_summary` của conv cũ — gọi bản
     **force** (bỏ qua ngưỡng `SUMMARY_TRIGGER`, `keep_recent=0`) để summary phủ
     hết conv kể cả khi đuôi ngắn (<60). Nếu conv rỗng/không có message sống thì
     bỏ qua bước nén.
   - `conv_cũ.archived_at = now`.
   - Tạo conv mới: `rolling_summary = conv_cũ.rolling_summary` (seed), 
     `summary_through_at = NULL`, `title = NULL` (đặt từ tin nhắn đầu như hiện tại).
   - Trả về conv mới.

**Thời điểm resolve**: chỉ lúc FE **mount** (qua `GET /conversations/active`). Giữa
phiên FE không giữ active id cũ; nếu vượt 150 giữa phiên vẫn chạy tốt nhờ rolling
summary, tới lần mount sau mới xoay. Idle-12h không thể xảy ra giữa phiên.

**Queue / queue_held / "tiếp tục công việc" GIỮ NGUYÊN** — luôn chạy trên active
conversation (spec §9 yêu cầu). Không sửa `continuity.py`, `worker.process_conversation`
phần queue.

## 5. API — 2 endpoint mới (trong `app/api/chat.py`)

- **`GET /api/v1/conversations/active`** → `ConversationOut`. Gọi
  `get_or_rotate_active_conversation` (tạo/xoay nếu cần), trả conv sống. Thay hẳn
  logic cold-start FE ("tạo mới mỗi lần mở app" + `convs[0]`).
- **`GET /api/v1/conversations/timeline?before=<cursor>&limit=50`** →
  `list[MessageOut]` + cursor kế. Gộp message **xuyên các conversation của user**
  theo `(created_at, id)` DESC, phân trang bằng cursor `before` (opaque encode của
  `created_at|id` message cũ nhất trang trước). FE cuộn lên nạp trang cũ hơn, đảo
  ngược để hiển thị. Quyền: chỉ conversation của chính actor (lọc qua
  `Conversation.user_id == actor.id` + `workspace_id`).
  - `MessageOut` thêm `conversation_id: uuid.UUID | None` (để FE vẽ ranh giới "cuộc
    trò chuyện mới" nếu muốn) — thêm field optional, không phá contract cũ.
  - Cursor: khuyến nghị format `"{created_at ISO}|{id}"` rồi urlsafe-base64; hoặc 2
    query param `before_at` + `before_id`. Chốt ở plan.
- Giữ nguyên `send_message`, `list_messages`, `list_requests`, ws — FE gửi vào
  active id lấy từ `/active`.

Sau khi đổi schema/endpoint: **chạy lại `python scripts/export_openapi.py`**.

## 6. Frontend

- **Bỏ New chat khỏi UX chính**:
  - `src/navigation/DrawerContent.tsx`: gỡ nút "New chat" đáy + hàm `newChat`.
  - `app/main/chat.tsx`: gỡ nút `create-outline` header + `newConversation` + biến
    module `coldStart`.
- **`chat.tsx` LIVE mode** (mở không có `?id`):
  - `GET /conversations/active` → lấy active id + title + `queue_held`.
  - `GET /conversations/timeline` (thay `listMessages`) → render một luồng liền
    mạch; cuộn lên đầu nạp trang timeline cũ hơn.
  - Mở ws trên active id; composer gửi vào active id. Queue/confirm/held UI giữ nguyên.
- **History ẩn** (route giữ khả năng xem lịch sử cũ):
  - Drawer "Gần đây" + màn `Conversations` vẫn mở conv theo `?id` = **chế độ xem
    lại read-only**: ẩn composer, hiện nút "Quay lại luồng hiện tại" (điều hướng về
    Chat LIVE). Không cho gửi vào conversation đã lưu trữ để tránh phân kỳ luồng.
- Đọc `frontend/DESIGN.md` + dùng token `src/ui/theme.ts` trước khi sửa screen.
- Xác minh: `npx tsc --noEmit` = 0 lỗi.

## 7. Test (TDD — test trước, code sau)

Backend (`pytest`, SQLite in-memory):
- **Rolling summary**: nén khi > 60 message → summary chứa nội dung cũ, `summary_through_at`
  đẩy đúng mốc; `_load_history` với `since` chỉ trả đuôi verbatim + summary vào
  system (không thành message); guard tool_result mồ côi vẫn giữ; `is_ack` vẫn loại.
  Mock `llm` trả text summary cố định.
- **Rotation**: tạo khi chưa có conv sống; xoay khi idle > 12h (inject `now`); xoay
  khi > 150 message; KHÔNG xoay khi còn việc dang dở (queued/running/deep_running/
  awaiting_confirmation/queue_held); seed `rolling_summary` conv mới từ conv cũ;
  `archived_at` conv cũ được set.
- **Timeline endpoint**: cursor phân trang đúng thứ tự xuyên ≥2 conversation; chỉ
  trả conv của chính user (không lộ conv user khác/workspace khác); shape `MessageOut`
  có `conversation_id`.
- **Active endpoint**: trả active; tạo nếu chưa có; quyền (không trả conv user khác).
- **Regression**: toàn bộ test queue/continuity cũ vẫn pass (logic per-conversation
  không đổi).

Gotcha đã biết: **SQLite trả datetime naive** (bài học period-bounds) — khi so idle
phải normalize cả hai vế về aware/UTC trước khi trừ.

## 8. Thứ tự implement (chi tiết ở plan)

1. Migration + 3 cột model.
2. `_load_history(since=)` + hằng số summary + `maybe_compress_history`.
3. Tiêm `rolling_summary` vào system prompt trong `run_agent_loop`.
4. Gọi `maybe_compress_history` trong `process_conversation`.
5. `get_or_rotate_active_conversation` + hằng số rotation.
6. Endpoint `GET /active` + `GET /timeline` + `MessageOut.conversation_id` + export OpenAPI.
7. FE: bỏ New chat + LIVE mode timeline + history read-only.
8. Verify: pytest full, tsc, cập nhật `PROJECT_CONTEXT.md`.

## 9. Không làm (YAGNI / ngoài phạm vi)

- embeddings/pgvector/indexer/`semantic_search` → Phase 6.
- Thread phụ theo chủ đề (report/project) → V2 (spec §9 ghi rõ).
- Sửa/xóa message, sửa summary thủ công.
- Morning brief / watcher / distiller → Phase 6 §10.2.
