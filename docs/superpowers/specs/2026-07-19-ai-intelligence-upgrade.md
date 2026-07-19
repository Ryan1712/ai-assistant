# Spec: Nâng cấp trí tuệ AI — Context-first Agent + Giao việc khép kín

> **Ngày:** 2026-07-19 · **Nguồn:** tổng hợp discussion CEO ↔ AI advisor
> **Trạng thái:** đã chốt hướng, sẵn sàng implement theo phase
> **Đối tượng đọc:** Claude Code / dev implement. Đọc kèm `CLAUDE.md` (quy ước) và
> `funtional-plan.md` (spec chức năng). Mọi quy ước trong `CLAUDE.md` vẫn áp dụng
> nguyên vẹn (workspace_id mọi bảng, permission ở service layer, actor từ JWT,
> TDD, export openapi khi đổi contract).

---

## 0. Bối cảnh & chẩn đoán

**Sản phẩm:** app mobile chat-first cho CEO SME — "bộ não thứ hai" (ghi nhớ hộ)
+ "kênh giao việc đáng tin" (một câu nói → vừa ghi sổ, vừa gửi lời tới người nhận).
9learning dùng nội bộ trước; workspace ~15 người, **~90% usage là CEO**, yêu cầu
phản hồi NHANH và chi phí thấp.

**Chẩn đoán hiện trạng** (đã verify trong code):

| Vấn đề | Nguyên nhân gốc |
|---|---|
| Trả lời chậm (6-12s) | Mỗi câu hỏi cần 2-4 vòng agent loop, mỗi vòng 1 round-trip Anthropic API. Model không phải thủ phạm chính. |
| Trả lời "ngu"/sai | (1) Haiku phải chọn giữa ~50 tool specs mỗi lượt — model nhỏ suy giảm mạnh khi không gian lựa chọn lớn. (2) Model phải tự đếm/cộng %/so deadline trên JSON thô. (3) Không có bối cảnh workspace sẵn — phải tra tool mới biết ai là ai. |
| Hội thoại dài tự lú | History cắt cứng `MAX_HISTORY_MESSAGES=80`, không summarize. |
| Nhầm người/task | Model tự khớp tên tiếng Việt (có/không dấu, trùng tên) từ list_users/list_tasks. |

**Nguyên tắc kiến trúc trung tâm:** *làm mọi việc nặng TRƯỚC khi câu hỏi được hỏi*
(precompute snapshot, index, analytics SQL) → lúc user nhắn, Haiku chỉ "đọc và nói",
0-1 vòng tool. **Nhanh và thông minh là cùng một giải pháp, không phải trade-off.**

**Các quyết định công nghệ đã chốt:**

| Công nghệ | Quyết định | Lý do |
|---|---|---|
| Agent framework | GIỮ custom loop (`app/agent/loop.py`), KHÔNG dùng LangChain/LangGraph | Loop hiện tại sạch, kiểm soát tốt confirmation/queue; arq đã là orchestration đủ dùng |
| Model chủ lực | GIỮ Haiku cho chat (nhanh, rẻ) + Sonnet cho "đường sâu" async | 90% usage CEO cần nhanh; đường sâu chạy nền nên chậm không sao |
| Vector DB | pgvector (extension Postgres), KHÔNG Chroma | Cách ly multi-tenant bằng chính filter workspace_id + permission join sẵn có; không thêm service phải vận hành |
| Embedding | Voyage `voyage-3.5` hoặc Cohere `embed-multilingual-v3` (API) | Tiếng Việt tốt, tích hợp nhanh; self-host BGE-M3 để sau |
| Fine-tuning | KHÔNG (Anthropic không mở, và sai công cụ) → thay bằng **example bank** few-shot tự lớn | Hiệu lực ngay, rollback được, không cần GPU |
| Multi-agent | CÓ, dạng agent chuyên trách chạy nền trong arq worker (distiller, watcher, analyst) — KHÔNG phải hội thoại giữa các agent | Giao tiếp qua DB/Redis, dễ debug |
| STT | Bake-off Whisper-qua-Groq vs Google STT v2 vs FPT.AI với 5-10 file ghi âm thật | `TranscriptionClient` đã abstract sẵn |
| Email provider | Resend hoặc Postmark (v1); SES khi scale | `EmailClient` protocol đã có, chỉ cắm impl thật |

---

## 1. Nguyên tắc thiết kế sản phẩm (nạp vào đầu trước khi code)

1. **North star: trợ lý điều hành (chief of staff) giỏi.** Hiểu ý dù nói tắt, tự
   điền chỗ trống bằng suy luận hợp lý, hỏi lại TỐI ĐA MỘT câu khi thật sự nhập
   nhằng (kèm đáp án bấm được), luôn cho sếp liếc-qua-rồi-gật thay vì tra hỏi.
2. **Draft-then-confirm.** Với lệnh mờ, AI KHÔNG hỏi vòng vo thu thập tham số —
   AI suy luận điền hết → trình thẻ nháp → user gật/sửa/hủy. Độ thông minh của
   sản phẩm nằm ở chất lượng bản nháp.
3. **Đơn vị nguyên tử = lời giao việc (directive), không phải task.** Một câu nói
   của CEO đồng thời là: (a) bản ghi vào sổ ("nay tôi đã giao cho Duy việc X"),
   (b) lời nhắn phải đến tay người nhận. Task là cấu trúc hóa của directive.
4. **Vòng lặp khép kín = "đáng tin".** CEO nói xong được phép QUÊN. Muốn vậy phải
   đảm bảo: lời đã đến → người nhận đã thấy → đã nhận việc (hoặc hỏi lại) → im
   lặng thì có người nhắc. Thiếu mắt xích nào CEO vẫn phải tự nhớ đi kiểm tra.
5. **Bất đối xứng adoption.** CEO (người trả tiền) phải nhận đủ giá trị NGAY CẢ KHI
   nhân viên không bao giờ cài app. Email là kênh sàn: giao việc luôn gửi cả
   in-app/push LẪN email; nhân viên khép được vòng lặp ngay trong email
   (ack 1-click, reply-by-email) không cần login/app.
6. **AI không bao giờ âm thầm sửa lời CEO.** Người nhận thấy cả bản cấu trúc
   (task/deadline rõ ràng) lẫn lời nguyên văn (verbatim) của CEO; thẻ nháp cho CEO
   xem trước CHÍNH XÁC người nhận sẽ thấy gì. Mọi directive truy ngược được về
   voice note/message gốc (bằng chứng).
7. **Im lặng là tin tốt.** Tin tốt (đã xác nhận, đúng hạn) gom vào brief; chỉ
   ngoại lệ (hỏi lại, xin dời, quá hạn im lặng) mới được phép ngắt CEO real-time.
   Escalation có tầng: nhắc người nhận trước (CEO không biết), báo CEO sau.
8. **Grounding tuyệt đối.** Mọi con số/tên/trạng thái trong câu trả lời PHẢI đến
   từ snapshot hoặc tool result của lượt này. Số liệu sinh từ SQL, model chỉ diễn
   giải — model KHÔNG BAO GIỜ tự làm toán trên dữ liệu thô.
9. **Guardrail ở tầng hệ thống, không ở prompt** (giữ nguyên quy ước hiện tại):
   permission ở service layer, actor từ JWT, confirmation do backend cưỡng chế.
   Áp dụng cho cả feature mới: snapshot/RAG/memory PHẢI lọc theo phạm vi quyền
   của actor đang chat (không nhét dữ liệu vượt quyền vào context của nhân viên).

---

## 2. Kiến trúc tổng thể

```
Tin nhắn user (text hoặc voice→STT)
        │
        ▼
  Router siêu nhẹ  (heuristic regex trước; Haiku 1-từ khi không chắc)
        │
   ┌────┴──────────────────────────┐
   ▼                               ▼
ĐƯỜNG NHANH (mặc định, ~90%)   ĐƯỜNG SÂU (phân tích/báo cáo)
Haiku, chạy trong agent loop    Ack ngay: "Đang phân tích, ~30s..."
+ Snapshot workspace tiêm sẵn   Sonnet + extended thinking,
+ RAG prefetch theo câu hỏi     chạy nền trong arq, push kết quả
+ Toolset rút gọn theo intent
+ Few-shot examples liên quan
→ 0-1 vòng tool, mục tiêu 2-4s
        │
        ▼
LỚP DỮ LIỆU CHUẨN BỊ SẴN (worker nền cập nhật liên tục)
Snapshot Redis · pgvector index · analytics SQL · memory facts · example bank
        ▲
        │
BACKGROUND AGENTS (arq jobs — "multi-agent" của hệ thống)
distiller (đêm: chưng cất memory) · watcher (cron: rủi ro deadline, morning brief,
escalation directive) · analyst (đường sâu) · indexer (embed khi data đổi)
```

---

## 3. Schema mới (Alembic migrations)

Mọi bảng đều có `workspace_id` index theo quy ước. Kiểu cột theo pattern
`app/models.py` hiện tại (Uuid PK default, DateTime(timezone=True), Enum...).

```python
class Directive(Base):
    """Lời giao việc — sự kiện giao tiếp có trách nhiệm. Khác Task (trạng thái
    công việc): 1 directive có thể không tạo task ("nhắc Duy nộp báo cáo");
    1 task có thể nhận nhiều directive theo thời gian."""
    __tablename__ = "directives"
    id, workspace_id
    created_by: FK users            # CEO hoặc manager (theo ma trận quyền giao việc hiện tại)
    recipient_id: FK users
    task_id: FK tasks, nullable     # gắn task nếu directive tạo/sửa task
    source_voice_note_id: FK voice_notes, nullable   # bằng chứng gốc
    source_message_id: FK messages, nullable
    verbatim_text: Text             # lời NGUYÊN VĂN của người giao — không được sửa
    structured_summary: Text        # bản AI diễn giải ("Dời deadline X sang 27/7 12:00")
    deadline: DateTime, nullable
    status: Enum(sent, seen, acked, question, renegotiate, done, cancelled)
    acked_at: DateTime, nullable
    remind_count: Integer, default 0
    created_at

class DirectiveDelivery(Base):
    """Theo dõi từng kênh gửi của 1 directive — nuôi escalation + đo hiệu quả kênh."""
    __tablename__ = "directive_deliveries"
    id, workspace_id
    directive_id: FK directives
    channel: Enum(in_app, push, email)
    sent_at, opened_at (nullable), clicked_at (nullable)
    provider_message_id: String, nullable

class WorkspaceMemory(Base):
    """Fact bền do distiller agent chưng cất hoặc user/CEO dặn trực tiếp.
    scope: 'workspace' (ai cũng nạp) | 'user:<uuid>' (chỉ nạp cho user đó).
    CEO xem/xóa được toàn bộ memory của workspace (trust)."""
    __tablename__ = "workspace_memories"
    id, workspace_id
    scope: String(64)
    content: Text                   # 1 fact ngắn, 1-2 câu
    source: String(32)              # 'distiller' | 'user_explicit'
    created_at, expires_at (nullable), archived_at (nullable)

class FewShotExample(Base):
    """Example bank — 'fine-tune bằng context'. Mỗi lần agent sai → dev/eval thêm
    cặp (câu hỏi, hành vi đúng). Retrieve top-k theo embedding vào system prompt."""
    __tablename__ = "few_shot_examples"
    id
    workspace_id: nullable          # NULL = example toàn cục dùng chung mọi workspace
    user_text: Text
    ideal_behavior: Text            # mô tả chuỗi tool + trả lời đúng
    embedding: Vector(1024)         # pgvector
    created_at

class Embedding(Base):
    """Index ngữ nghĩa xuyên suốt. source_type: task | task_update | comment |
    note | voice_transcript | skill | chat_message."""
    __tablename__ = "embeddings"
    id, workspace_id (index)
    source_type: String(32), source_id: Uuid   # unique(source_type, source_id, chunk_no)
    chunk_no: Integer, default 0
    content: Text                   # chunk text đã embed
    embedding: Vector(1024)         # pgvector, index HNSW
    created_at

# Sửa bảng có sẵn:
# conversations: thêm cột `rolling_summary: Text, default ""`,
#                `archived_at: DateTime nullable` (phục vụ xoay conversation ngầm)
# ChatRequest.pending_action: giữ nguyên cấu trúc, thêm hỗ trợ dạng
#                {"kind": "proposal", "actions": [...], "reasoning": str} (mục 5)
```

Config mới trong `Settings` (`app/config.py`):

```python
model_fast: str = "claude-haiku-4-5"       # đổi tên từ model_chat (giữ alias cũ đọc được)
model_smart: str = "claude-sonnet-4-6"     # đường sâu, distiller chất lượng cao, report summary
embedding_provider: str = "voyage"          # voyage | cohere | mock
embedding_api_key: str = ""
email_provider: str = "mock"                # mock | resend | postmark
email_api_key: str = ""
email_from_domain: str = "9learning.edu.vn"
snapshot_ttl_seconds: int = 300             # fallback refresh nếu hook lỡ
```

---

## 4. Phase 0 — Nền móng đo lường (LÀM TRƯỚC MỌI FEATURE)

> Lý do: 5 phase sau đều cần vòng lặp "thấy lỗi → chẩn đoán → sửa → chặn tái phát".

### 4.1 Agent tracing
- Bảng `agent_traces` (hoặc mở rộng UsageLog): mỗi ChatRequest ghi
  `iterations, tools_called (list: name, latency_ms, input/output rút gọn 500 ký tự),
  stop_reason, model, route (fast|deep), total_latency_ms`.
- Endpoint debug `GET /api/v1/admin/traces/{chat_request_id}` (chỉ CEO/root, hoặc
  env dev). Tùy chọn: tích hợp Langfuse self-host sau — v1 bảng DB là đủ.

### 4.2 Eval harness với model thật
- `backend/evals/` (ngoài pytest CI thường): ~40-50 scenario tiếng Việt thực tế,
  format YAML: `{user_text, expected_tools: [...], expected_behavior: mô tả,
  forbidden: [...]}`. Ví dụ bắt buộc có:
  - "giao task báo cáo thuế cho Hà deadline thứ 6" → create/assign đúng
  - "khóa acc thằng Nam" → gọi lock_user → awaiting_confirmation (không hỏi bằng lời)
  - nhân viên đòi tạo project → từ chối, không gọi tool
  - "bảo Duy sáng thứ 2 tuần sau xong deadline nhé" → propose_actions (sau Phase 3)
  - tiếng Việt không dấu, viết tắt, tên trùng
- Runner: script gọi API thật, chấm deterministic bằng so khớp tool call (tên tool
  + tham số chính). Chạy tay TRƯỚC MỖI LẦN đổi system prompt / model / toolset.
- Quy ước: mỗi bug hành vi được fix → thêm 1 scenario tương ứng.

### 4.3 Incremental prompt caching + model routing config
- `llm_client.py`: hiện đã cache system + tools. THÊM `cache_control` vào message
  cuối của history mỗi lượt (incremental caching) → giảm ~60-70% input cost.
- Thêm `model_fast/model_smart` vào Settings; loop nhận model qua tham số.

**Acceptance Phase 0:** xem được trace của mọi request; eval suite chạy được và
pass baseline; UsageLog ghi nhận cache_read tăng rõ sau incremental caching.

---

## 5. Phase 1 — Workspace Snapshot (kỹ thuật ăn tiền nhất)

Bản chất: worker duy trì bức tranh workspace dạng text nén (~2-4k token) trong
Redis, tiêm vào system prompt (có cache_control) → 80% câu hỏi thường nhật của CEO
("dự án A sao rồi?", "ai đang rảnh?", "hôm nay có gì cần chú ý?", "bảo Duy...")
trả lời NGAY LƯỢT ĐẦU, 0 tool call, số liệu đúng vì SQL tính sẵn.

### 5.1 Nội dung snapshot (per-workspace, per-role-scope)
```
## Trạng thái công ty (cập nhật {HH:MM})
### Projects
[P1] Marketing Q3 — 68%, 12 task (2 blocked, 1 trễ hạn), deadline 15/8 ⚠ nguy cơ trễ
...
### Nhân sự & khối lượng
Duy (Nhân viên, manager: Hà) — 1 task đang làm: "Thiết kế landing page" (P1, 40%, hạn 30/7)
Nam (Kế toán) — 5 task mở, 1 trễ hạn, cập nhật gần nhất 2 ngày trước
...
### Hôm nay
3 task đến hạn: ... | Cập nhật mới nhất: Nam báo blocked task X lúc 08:40
### Việc CEO đã giao đang chờ xác nhận (directive)   ← sau Phase 3
Duy — "Thiết kế landing page" hạn 27/7 — gửi 14:00 hôm qua, CHƯA xác nhận
```

### 5.2 Cơ chế
- Builder: `app/services/snapshot_service.py` — các query aggregate SQL (KHÔNG gọi
  LLM), render text template. **Snapshot dựng THEO PHẠM VI QUYỀN**: CEO thấy toàn
  bộ; manager thấy nhánh của mình; employee thấy việc của mình. Cách làm: build 1
  snapshot đầy đủ + hàm cắt theo `visible_user_ids/visible_task_ids` sẵn có, hoặc
  build theo role — chọn cách rẻ hơn khi implement, miễn KHÔNG lộ vượt quyền.
- Refresh: hook debounce (vài giây, qua arq enqueue) vào các hàm write của
  work_service / directive service; fallback TTL `snapshot_ttl_seconds`.
- Nạp: trong `run_agent_loop`, sau instruction block: `system_prompt += snapshot`.
  Đặt cache_control hợp lý (snapshot đổi thường xuyên → cân nhắc đặt SAU block
  system+tools tĩnh để không phá cache của phần tĩnh).

**Acceptance:** hỏi "tình hình dự án X?", "Duy đang làm gì?" → trả lời đúng,
0 tool call (verify bằng trace), p50 latency < 4s.

---

## 6. Phase 2 — propose_actions + luật 3 mức + resolver + toolset động

### 6.1 Tool `propose_actions` (primitive trung tâm)
```python
_register("propose_actions",
    "Trình bản nháp 1+ hành động cho người dùng duyệt trước khi thực thi. "
    "BẮT BUỘC dùng khi: (a) phải SUY LUẬN đối tượng (đoán task/người/deadline từ "
    "ngữ cảnh thay vì user nói tường minh), (b) hành động khó đảo ngược, "
    "(c) gộp nhiều hành động một lượt. Gọi NGAY, hệ thống tự hiện thẻ xác nhận.",
    input_model: {actions: [{tool_name, tool_input, display_text}], reasoning: str})
```
- Backend: xử lý như sensitive tool hiện tại — set `awaiting_confirmation`,
  `pending_action = {"kind": "proposal", ...}`. `resolve_confirmation` mở rộng:
  approved → chạy tuần tự từng action (validate từng tool_name có tồn tại + actor
  đủ quyền qua service layer như thường); mỗi action fail → ghi lỗi vào result,
  làm tiếp action sau (giống hàng đợi: bỏ qua, báo rõ).
- FE: render card từ `pending_action` — actions dạng bảng, nút Xác nhận/Sửa/Hủy.
  (FE có thể ship v1 chỉ Xác nhận/Hủy; Sửa = user gõ đè bằng lời.)
- Validate: tool trong actions KHÔNG được là sensitive tool khác (tránh lách
  confirmation riêng của lock_user...) — nếu có, tách flow như cũ.

### 6.2 Luật hành xử 3 mức (đưa vào system prompt — xem mục 11)
| Tình huống | Hành vi |
|---|---|
| Tường minh + đảo ngược được ("cập nhật task X lên 80%") | Làm ngay, echo đầy đủ đối tượng ("Đã cập nhật 'Báo cáo thuế Q3' của Nam lên 80%") |
| Phải suy luận đối tượng / khó đảo ngược / nhiều hành động | `propose_actions` |
| Sensitive (khóa acc, xóa, email tự soạn) | Confirm bắt buộc (cơ chế hiện tại) |

### 6.3 Resolver tools (diệt lỗi nhầm người/task)
```python
_register("resolve_person", "Tìm người theo tên/biệt danh, chịu được không dấu/"
    "viết tắt. Trả match duy nhất HOẶC danh sách ứng viên nếu nhập nhằng HOẶC "
    "not_found. TUYỆT ĐỐI không đoán khi >1 ứng viên.", ...)
_register("resolve_task", tương tự cho task theo tiêu đề/mô tả)
```
- Impl: normalize NFD bỏ dấu (tái dùng hàm trong `app/services/continuity.py`) +
  `pg_trgm` similarity. Kết quả ≥2 → `{"ambiguous": true, "candidates": [...]}` +
  system prompt quy định: hỏi lại 1 câu kèm lựa chọn cụ thể, không tự chọn.
- Lưu ý: khi snapshot đã có danh bạ, resolver là lớp dự phòng cho ca khó
  (trùng tên, tên lạ) — model ưu tiên khớp từ snapshot trước.

### 6.4 Toolset động theo intent (Haiku hết "ngộp" 50 tools)
- `TOOL_GROUPS` trong `app/agent/tools.py`:
  `core` (resolver, propose_actions, get_task, search... — luôn nạp) +
  `work` | `insight` | `admin` | `reporting` | `skill_instruction` | `personal`
  (note/voice/notification).
- Router (mục 8) trả nhóm → loop nạp `core + nhóm` (~10-15 tools). Không chắc →
  nạp full 50 như cũ (fallback an toàn).

### 6.5 Tool result design (chống hallucination)
- Result rỗng phải NÓI RÕ NGHĨA: `{"tasks": [], "note": "Không có task nào khớp
  bộ lọc deadline tuần này"}` — không trả `[]` trần.
- Error viết cho model đọc, chỉ hướng hành động: `{"error": "not_found",
  "hint": "Không có project tên gần giống 'marketing'. Gọi list_projects."}`.
- Rà lại toàn bộ tools hiện có theo 2 quy tắc trên.

**Acceptance:** "bảo Duy sáng thứ 2 tuần sau xong deadline nhé" (Duy 1 task) →
1 lượt LLM → thẻ propose_actions đúng task đúng deadline; (Duy 3 task) → 1 câu hỏi
kèm 3 lựa chọn. Eval scenarios nhóm resolver/proposal pass.

---

## 7. Phase 3 — Directive: giao việc khép kín + email delivery

### 7.1 Service `app/services/directive_service.py`
- `create_directive(db, actor, *, recipient_id, task_id, verbatim_text,
  structured_summary, deadline, source_voice_note_id, source_message_id)`:
  - Quyền: theo ma trận giao việc hiện tại (CEO; manager cho nhân viên dưới quyền
    — khớp logic assign_task/permissions.py hiện có).
  - Ghi Directive (status=sent) → gửi đa kênh (7.2) → ghi DirectiveDelivery/kênh.
- `ack_directive(db, *, directive_id, via)` / `mark_seen` / `raise_question` /
  `renegotiate(new_deadline_proposal, reason)`.
- State machine: sent → seen → acked | question | renegotiate → done | cancelled.

### 7.2 Delivery đa kênh — directive LUÔN đi mọi kênh
1. **In-app + push**: qua helper `notify()` sẵn có, type `directive_assigned`,
   payload đủ render card trong app người nhận với nút
   [Nhận việc] [Hỏi lại] [Xin dời hạn].
2. **Email** (kênh sàn — bất đối xứng adoption):
   - Impl `ResendEmailClient` / `PostmarkEmailClient` sau `EmailClient` protocol
     hiện có; giữ MockEmailClient cho test. Setup SPF/DKIM/DMARC cho
     `email_from_domain` (tài liệu hóa trong README).
   - From: `troly@{domain}`, display name "{Tên CEO} (CEO) — qua Trợ lý AI",
     **Reply-To = email thật của người giao**. (Send-as OAuth = V2/Advanced.)
   - Nội dung: bảng cấu trúc (việc/hạn/project) + khối "Lời nhắn gốc" in
     `verbatim_text` + link nghe ghi âm (nếu có source_voice_note) + nút lớn
     **"Xác nhận đã nhận việc"** + dòng "Trả lời email này để hỏi lại/xin dời hạn".
   - **Ack 1-click KHÔNG CẦN LOGIN**: nút = signed URL
     `GET /api/v1/public/directives/ack?token=...` — token JWT ký
     (directive_id, recipient_id, exp dài, single-purpose claim), endpoint public
     đánh dấu acked + trang HTML tĩnh "Đã xác nhận với {tên người giao} ✓".
     Idempotent. KHÔNG trả thêm dữ liệu workspace nào khác.
   - Header `In-Reply-To`/`References` để thread gọn trong hộp thư người nhận.
3. Ghi `DirectiveDelivery` mỗi kênh; provider webhook delivered/opened (nếu có) →
   cập nhật opened_at (V1 làm outbound + clicked qua ack link là đủ; open pixel
   = V2).

### 7.3 Escalation (thêm vào cron watcher — mục 10.2)
- Quét directives status=sent/seen quá 24h: nhắc người nhận (push + email nhắc),
  `remind_count += 1` — CEO KHÔNG bị làm phiền.
- Quá 48h (remind_count ≥ 1 vẫn im): notify CEO "Duy chưa xác nhận việc X đã 2
  ngày (đã nhắc 1 lần)".
- Tin tốt (acked) KHÔNG push CEO — gom vào morning brief:
  "5/5 việc anh giao hôm qua đã được xác nhận".

### 7.4 Tích hợp agent
- Tool mới `create_directive` (nạp nhóm `work`): agent gọi BÊN TRONG
  propose_actions khi câu nói là lời giao việc. Flow chuẩn cho
  "bảo Duy ... xong deadline nhé":
  `propose_actions(actions=[{update_task deadline...}, {create_directive ...}])`
  → thẻ nháp 2 nửa: "Ghi vào sổ" (task/deadline) + "Gửi cho Duy" (preview đúng
  nội dung email/push kèm verbatim + toggle đính ghi âm).
- Analytics tool `get_directive_status` (nhóm `insight`): "tuần này tôi giao gì",
  "ai chưa xác nhận", "Duy còn nợ tôi mấy việc" — 1 câu SQL, model diễn giải.
- Snapshot thêm section "Việc đã giao đang chờ xác nhận".

### 7.5 Phía người nhận trong app (FE — làm song song)
- Chat của người nhận hiện card directive + 3 nút. "Nhận việc" → ack.
  "Hỏi lại" → gửi câu hỏi thành comment vào task + notify người giao (v1 đơn
  giản). "Xin dời hạn" → v1: dạng câu hỏi thường; **V2**: thẻ đàm phán — AI đóng
  gói đề nghị + lý do → thẻ về CEO [Đồng ý dời / Giữ nguyên / Nhắn lại].
- **V2**: inbound reply-by-email (address `directive-{id}@reply.{domain}`,
  Postmark inbound webhook → arq job → AI phân loại ack/question/renegotiate).

**Acceptance:** một câu voice "bảo Duy..." → thẻ nháp 2 nửa → 1 gật → task đổi
deadline + Directive tạo + email thật tới hộp thư (test bằng mailbox thật) + nút
ack trong email hoạt động không cần login → trạng thái acked hiện trong
get_directive_status + snapshot. Escalation cron test bằng time-freeze.

---

## 8. Phase 4 — Router + đường sâu async

### 8.1 Router
- Tầng 1 heuristic (0ms, regex tiếng Việt normalize không dấu): các từ
  "phân tích|đánh giá|vì sao|tại sao|so sánh|nhận xét|báo cáo chi tiết|tổng kết"
  → `deep`; từ nhóm admin ("khóa|mở khóa|mời|phân quyền") → `admin`; v.v.
- Tầng 2 (chỉ khi heuristic không chắc): 1 lượt `model_fast`, system prompt 5
  dòng, output đúng 1 từ: `work|insight|admin|reporting|skill|personal|deep`.
- Kết quả quyết định: toolset nạp (6.4) + fast/deep path.

### 8.2 Đường sâu (async-with-ack)
- Route=deep: agent loop lượt đầu bằng `model_fast` CHỈ để ack
  ("Đang phân tích toàn bộ dự án, khoảng 30 giây — tôi sẽ báo khi xong.") + enqueue
  arq job `run_deep_analysis(chat_request_id)`.
- Job: `model_smart` + extended thinking, toolset `insight` + analytics tools,
  MAX_ITERATIONS riêng cao hơn; xong → ghi Message assistant + publish
  `request_done` + push notification nếu app đang background.
- UX giống Deep Research: user được BÁO TRƯỚC việc này nặng nên không thấy chậm.

**Acceptance:** "đánh giá rủi ro toàn bộ project tháng này" → ack < 3s → kết quả
Sonnet đẩy về sau; câu thường vẫn đi Haiku. Trace ghi đúng route.

---

## 9. Phase 5 — Session model: một luồng duy nhất

Lý do gốc: mô hình nhiều-chat của ChatGPT tồn tại vì ở đó chat = bộ nhớ. Kiến
trúc này đã chuyển bộ nhớ ra snapshot/memory/pgvector → chat chỉ là nơi ra lệnh
→ KHÔNG bắt user quản lý chat. UX = "nhắn cho trợ lý" một luồng liên tục kiểu Zalo.

- **Rolling summary:** history vượt ~60 messages → 1 lượt `model_fast` nén phần cũ
  vào `conversations.rolling_summary`; `_load_history` trả
  `[summary block] + messages gần nhất`. Giữ nguyên guard tool_result mồ côi.
- **Xoay conversation ngầm (server-side):** user có "active conversation"; tự
  sang trang khi idle > 12h HOẶC messages > 150: archive conversation cũ
  (`archived_at`), tạo conversation mới, seed rolling_summary của conversation cũ
  làm context mở đầu. FE render tất cả thành MỘT timeline liền mạch (endpoint
  list messages phân trang xuyên các conversation của user). **Toàn bộ logic
  queue / queue_held / "tiếp tục công việc" per-conversation GIỮ NGUYÊN** — chỉ
  luôn hoạt động trên conversation active.
- **Ký ức xuyên session:** chat messages được index vào `embeddings`
  (source_type=chat_message) → "tuần trước tôi dặn gì về hợp đồng X?" = retrieval,
  không phụ thuộc chat nào đang mở.
- UX chính KHÔNG có nút "New chat". (Route ẩn giữ khả năng xem lịch sử cũ.)
- V2: thread phụ theo chủ đề (gắn report/project).

**Acceptance:** hội thoại 200+ messages không fail, không lú đầu chuyện (eval:
nhắc lại thông tin từ đầu hội thoại qua summary); sang ngày mở app vẫn một luồng,
"hôm qua tôi dặn gì?" trả lời đúng.

---

## 10. Phase 6 — Lớp dữ liệu thông minh còn lại

### 10.1 Analytics tools (model không bao giờ tự làm toán)
Nhóm `insight`, mỗi tool = SQL aggregate lọc theo phạm vi quyền actor:
- `get_workload_summary` — mỗi người: task mở, trễ hạn, % TB, lần cập nhật cuối.
- `get_project_health` — 1 project: tiến độ, blocked, đứng im >N ngày, sắp hạn.
- `get_progress_stats` — theo kỳ tuần/tháng, so kỳ trước.
- `get_directive_status` — (đã nêu 7.4).

### 10.2 Background agents (arq)
- **watcher** (cron mỗi giờ + 07:00): rule engine chọn ứng viên (deadline gần +
  percent đứng im; directive quá hạn ack) → 1 lượt `model_fast` viết lời nhắc có
  ngữ cảnh → notify. 07:00: **morning brief** cho CEO = dashboard service +
  directive status + 1 lượt LLM tổng hợp → push + card đầu chat.
- **distiller** (cron đêm, `model_fast`): đọc hội thoại + updates trong ngày →
  chưng cất fact bền vào `workspace_memories` (dedupe theo embedding similarity).
  Facts nạp vào system prompt (block "Ghi nhớ dài hạn", giới hạn ~800 token,
  ưu tiên mới + scope khớp actor). CEO có tool `list_memories`/`forget_memory`.
- **indexer**: hook create/update (task, update, comment, note, transcript,
  chat message) → enqueue embed → upsert `embeddings`.
- **report summary**: chèn 1 lượt `model_smart` vào `generate_report` — viết 5-7
  dòng executive summary (bất thường, quá tải, blocked) đặt đầu sheet Excel +
  trả trong chat.

### 10.3 RAG prefetch + tool
- Trong worker, TRƯỚC agent loop: embed câu user (song song với load history) →
  top-k (k≈6-8) từ `embeddings` **lọc workspace_id + phạm vi quyền** → block
  "## Dữ liệu liên quan" cuối system prompt. Điểm similarity thấp → bỏ block.
- Tool `semantic_search` (nhóm core) để model tự đào thêm.
- Hybrid v2: kết hợp pg_trgm/FTS + vector (RRF).

### 10.4 Example bank
- Retrieve top 3-5 `few_shot_examples` theo embedding câu user → block
  "## Ví dụ xử lý đúng" trong system prompt.
- Nguồn: mỗi eval scenario fail đã fix → thêm example; CEO/dev thêm tay qua
  admin endpoint.

### 10.5 Onboarding (làm khi bắt đầu có workspace mới thật)
- Workspace mới → seed tin nhắn AI mở màn (scripted, 0 LLM) + FE quick-reply
  chips: [Dựng project đầu tiên] [Tôi có file Excel công việc cũ] [Mời nhân viên]
  [Xem thử làm được gì].
- **Coach block**: cờ `has_projects/has_tasks/has_members/has_first_report` (query
  rẻ) — còn cờ chưa bật → chèn block system prompt: "sau mỗi yêu cầu, gợi ý NGẮN
  1 câu bước hợp lý tiếp theo"; đủ mốc tự tắt.
- **Import Excel/text**: user paste/upload → AI bóc → MỘT thẻ `propose_actions`
  lớn (project + N task + phụ trách) — tái dùng nguyên primitive Phase 2.

---

## 11. System prompt mới (bản nháp — tinh chỉnh qua eval)

Cấu trúc block, thứ tự tối ưu cache (tĩnh trước, động sau):

```
[BLOCK TĨNH — cache]
Bạn là trợ lý điều hành của công ty — như một chief of staff giỏi. Luôn tiếng Việt.
{danh tính actor từ JWT + vai trò — như hiện tại}
{thời gian VN — như hiện tại}

# Nguyên tắc hành xử
1. GROUNDING: mọi con số, tên người, trạng thái trong câu trả lời PHẢI đến từ
   "Trạng thái công ty", "Dữ liệu liên quan", hoặc tool result của lượt này.
   Không có dữ liệu → nói thẳng "chưa có thông tin", tuyệt đối không suy đoán.
2. BA MỨC HÀNH ĐỘNG:
   - Yêu cầu tường minh + dễ đảo ngược → làm ngay, echo đầy đủ đối tượng đã tác động.
   - Phải SUY LUẬN đối tượng (đoán task/người/deadline từ ngữ cảnh) HOẶC khó đảo
     ngược HOẶC nhiều hành động → gọi propose_actions. Điền sẵn mọi thứ bằng suy
     luận tốt nhất, kèm reasoning 1 câu.
   - Hành động nhạy cảm → gọi tool ngay, hệ thống tự hiện xác nhận (như hiện tại).
3. NHẬP NHẰNG: resolve từ "Trạng thái công ty" trước; vẫn ≥2 ứng viên → hỏi lại
   ĐÚNG MỘT câu kèm danh sách lựa chọn cụ thể. Không bao giờ tự chọn thay.
4. LỜI GIAO VIỆC ("bảo X làm Y", "nhắn X...", giao việc kèm deadline): luôn gồm
   2 nửa — ghi sổ (task/deadline) + gửi tới người nhận (create_directive, giữ
   NGUYÊN VĂN lời người giao trong verbatim_text). Gộp cả hai vào 1 propose_actions.
5. Trả lời NGẮN GỌN, đúng trọng tâm. Quyền hạn: {như hiện tại}. Skill: {như hiện tại}.

[BLOCK ĐỘNG — sau phần cache tĩnh]
# Chỉ dẫn từ CEO công ty      ← instruction_service (hiện tại)
# Ghi nhớ dài hạn              ← workspace_memories (Phase 6)
# Trạng thái công ty           ← snapshot (Phase 1)
# Dữ liệu liên quan            ← RAG prefetch (Phase 6)
# Ví dụ xử lý đúng             ← example bank (Phase 6)
# Chế độ dẫn dắt               ← coach block, chỉ workspace mới (Phase 6)
# Tóm tắt hội thoại trước      ← rolling_summary (Phase 4/5)
```

---

## 12. Thứ tự implement & phân nhánh

| Phase | Nội dung | Ước lượng | Nhánh |
|---|---|---|---|
| 0 | Tracing + eval harness + incremental caching + model config | 3-4 ngày | AI dev |
| 1 | Workspace snapshot | 2-3 ngày | AI dev |
| 2 | propose_actions + 3 mức + resolver + toolset động + rà tool results | 4-5 ngày | AI dev (FE: card proposal) |
| 3 | Directive + email thật + ack 1-click + escalation | 1 tuần | AI dev (FE: card directive 2 nửa + phía người nhận) |
| 4 | Router + đường sâu async | 3-4 ngày | AI dev |
| 5 | Rolling summary + xoay conversation + timeline FE | 3-4 ngày | chia BE/FE |
| 6 | pgvector + analytics + agents nền + example bank + onboarding | 1.5-2 tuần, cắt nhỏ được | chia |

Mỗi phase: TDD theo quy ước, thêm eval scenarios tương ứng, chạy eval suite trước
merge, export openapi nếu đổi contract, cập nhật PROJECT_CONTEXT.md.

## 13. Quyết định còn MỞ (đừng tự quyết khi implement — hỏi lại)
1. STT provider (chờ bake-off với file ghi âm thật của 9learning).
2. Reply email của người nhận: v1 Reply-To về hộp thư người giao (đã chốt tạm);
   V2 inbound qua AI — mức độ AI "đứng giữa" cần CEO duyệt trải nghiệm.
3. Ngưỡng cụ thể: idle xoay conversation (8h vs 12h), escalation (24/48h),
   ngưỡng rolling summary — để config, tune bằng dùng thật.
4. Send-as OAuth (gửi từ chính Gmail CEO) — để V2/gói Advanced.
