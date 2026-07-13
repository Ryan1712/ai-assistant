# Plan 8 — "Tiếp tục công việc" (funtional-plan 5.7)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Checkbox (`- [ ]`) để tracking.

**Goal:** Mất mạng / đóng app → hàng đợi chat **không tự chạy tiếp**; việc dang dở được ghi nhớ; chỉ khi user gõ **"tiếp tục công việc"** thì AI mới làm nốt (spec 5.7 + mục 9).

**Architecture:** WS disconnect (socket cuối cùng của conversation) → set cờ `conversations.queue_held`. Worker kiểm tra cờ mỗi vòng lặp (như đã kiểm tra `awaiting_confirmation`) → dừng xử lý khi held. Tin nhắn mới match cụm "tiếp tục công việc" (không phân biệt hoa thường/dấu/khoảng trắng thừa) → clear cờ; request của chính tin đó vẫn vào queue như thường nên AI trả lời nó SAU KHI làm nốt việc cũ — đúng ngữ nghĩa "làm nốt". Presence đếm in-process (single API instance — đủ cho hiện tại; multi-instance cần chuyển redis, ghi chú trong code).

**Tech Stack:** BE như cũ (không thêm dependency). FE: banner + nút trong màn chat.

## Global Constraints (CLAUDE.md)
- workspace_id mọi bảng; quyền ở service layer; actor từ JWT; TDD, mỗi task 1 commit; export openapi khi đổi contract.

## Quyết định thiết kế
- **Ngữ nghĩa hold:** hold = TOÀN BỘ queue của conversation dừng (kể cả tin mới gửi khi đang held — vì queue tuần tự, không thể chạy tin mới trước tin cũ mà không phá thứ tự lịch sử). FE hiển thị banner giải thích. Request đang `running` lúc disconnect: chạy nốt request đó (worker chỉ chặn TRƯỚC khi lấy item kế tiếp).
- **Chỉ socket cuối cùng disconnect mới hold** (user mở 2 thiết bị: tắt 1 cái không dừng queue) — đếm presence per-conversation.
- **Reconnect KHÔNG tự clear hold** — spec: chỉ cụm từ "tiếp tục công việc" mới resume.
- **Chỉ hold khi có việc dang dở** (queued/running); queue rỗng thì disconnect không set cờ.
- **Match cụm từ:** casefold + strip + gộp khoảng trắng + bỏ dấu (NFD, đ→d) rồi so `"tiep tuc cong viec"`. Match khi KHÔNG held → tin nhắn thường, vô hại.
- **Không thêm endpoint mới** — resume đi qua chính POST messages (YAGNI); nút FE chỉ là shortcut gửi đúng cụm từ.

### Task 1: Service presence + continuity (TDD)
- [x] `app/services/presence.py`: đếm socket per-conversation, in-process (`dict[uuid.UUID, int]` module-level). API: `connect(conversation_id) -> int` (count sau khi tăng), `disconnect(conversation_id) -> int` (count sau khi giảm, floor 0, xóa key khi 0), `reset()` (cho test). Docstring ghi rõ giới hạn single-instance.
- [x] `app/services/continuity.py`:
  ```python
  RESUME_PHRASE = "tiep tuc cong viec"

  def _normalize(text: str) -> str:
      # casefold, đ→d, bỏ dấu (NFD bỏ combining), gộp khoảng trắng
      text = text.casefold().replace("đ", "d")
      text = unicodedata.normalize("NFD", text)
      text = "".join(c for c in text if not unicodedata.combining(c))
      return " ".join(text.split())

  def is_resume_phrase(text: str) -> bool:
      return _normalize(text) == RESUME_PHRASE

  async def hold_queue_if_pending(db, conversation_id) -> bool:
      # True nếu có request queued/running → set conversations.queue_held=True + commit
  ```
- [x] Test `tests/test_continuity.py`: phrase — `"tiếp tục công việc"`, `"  Tiếp Tục  Công Việc "`, `"TIEP TUC CONG VIEC"` → True; `"tiếp tục"`, `"làm nốt công việc"` → False. Presence: 2×connect → 2; disconnect → 1; disconnect → 0; disconnect lần nữa vẫn 0. hold: conv có request queued → True + cờ set; conv rỗng → False + cờ không set.
- [x] Commit `feat(be): presence + continuity service (resume phrase, hold queue)`. (Ghi chú thực thi: cột model `queue_held` gộp vào commit này vì `hold_queue_if_pending` cần nó.)

### Task 2: Model + worker gate (TDD)
- [x] `models.py`: `Conversation.queue_held: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")`.
- [x] `worker.py::process_conversation`: trong vòng while, sau check `awaiting_confirmation`, thêm:
  ```python
  conv = await db.get(Conversation, conversation_id)
  if conv is not None and conv.queue_held:
      return  # 5.7: mất mạng → không tự chạy tiếp, chờ "tiếp tục công việc"
  ```
- [x] Test thêm vào `tests/test_worker.py`: conversation `queue_held=True` có 1 request queued → `process_conversation` return, request vẫn `queued`, `llm.calls == 0`. Mirror fixture style test hiện có (Workspace/User/Conversation/ChatRequest + FakeLLMClient + FakeEventPublisher).
- [x] Commit `feat(be): worker dung xu ly queue khi conversation queue_held`.

### Task 3: Wire WS disconnect + resume phrase + contract (TDD)
- [x] `app/api/ws.py::conversation_ws`: sau `accept()` → `presence.connect(conversation_id)`; trong `finally`: `if presence.disconnect(conversation_id) == 0: await continuity.hold_queue_if_pending(db, conversation_id)`.
- [x] `app/api/chat.py::send_message`: sau khi tạo req/Message, trước commit:
  ```python
  if conv.queue_held and continuity.is_resume_phrase(body.content):
      conv.queue_held = False
  ```
  (enqueue_conversation đã gọi sẵn sau commit — không đổi.)
- [x] `schemas.py::ConversationOut`: thêm `queue_held: bool = False`.
- [x] Test (thêm `tests/test_continuity_api.py`): (1) conv held + POST message "tiếp tục công việc" → GET /conversations thấy `queue_held == False` và request mới nằm CUỐI queue; (2) conv held + POST message thường → vẫn held; (3) conv không held + POST "tiếp tục công việc" → vẫn không held, request tạo bình thường; (4) GET /conversations trả field `queue_held`.
- [x] Commit `feat(be): ws disconnect hold queue + resume bang cum tiep tuc cong viec`.

### Task 4: Migration + openapi
- [x] Migration tay: `conversations.queue_held` Boolean NOT NULL server_default false. Full pytest (206 passed). `python scripts/export_openapi.py`. Commit `chore(be): plan8 migration + openapi refresh`.

### Task 5: FE banner + nút tiếp tục
- [x] `src/api/chat.ts`: `Conversation` thêm `queue_held: boolean`.
- [x] `app/(main)/chat.tsx`: state `held` (khởi tạo từ conversation lúc mount). Khi `held`:
  banner (màu `warningBg`/`warningText` theo theme) trên khối queue: "⏸ Việc dang dở đang chờ — gõ 'tiếp tục công việc' để AI làm nốt" + nút "▶ Tiếp tục" (gửi đúng cụm `tiếp tục công việc` qua sendMessage, set `held=false` optimistic). Gửi tay tin nhắn match cụm (so sánh phía FE: lowercase+trim) cũng set `held=false`.
- [x] Typecheck + expo export. Commit `feat(fe): banner tiep tuc cong viec + nut resume queue`.

## Ghi chú
- Presence in-process: nếu sau này API chạy nhiều instance → chuyển counter sang redis (INCR/DECR + TTL), interface giữ nguyên.
- FE không thể biết held đổi real-time khi chính nó offline (hiển nhiên) — fetch lại `GET /conversations` lúc mount là đủ.
