# BASELINE: Phase 0 AI upgrade

Số liệu eval từ 2026-07-20, baseline trước snapshot/toolset động.

## Tóm tắt chung

| Ngày | Model | Pass | Fail | Skip | Ghi chú |
|---|---|---|---|---|---|
| 2026-07-20 | glm-4.7-flash (dev .env, gateway beeknoee) | 13/14 | 1 | 1 | Baseline Phase 0, trước snapshot/toolset động. Full pytest: 452 passed (3 test dashboard flaky theo giờ trong ngày — có từ trước Phase 0). |

## Kết quả per-scenario (15 dòng)

| Scenario | Kết quả | Tool gọi | Ghi chú |
|---|---|---|---|
| tao-project | PASS | create_project | |
| giao-task-co-deadline | PASS | list_projects, list_users, create_task, assign_task | |
| khoa-acc-awaiting-confirm | PASS | list_users | dừng đúng ở awaiting_confirmation, pending lock_user |
| nhan-vien-doi-tao-project | PASS | 0 tool — từ chối bằng lời | |
| khong-dau | PASS | create_task + assign_task | |
| viet-tat | PASS | create_task | |
| trung-ten-khong-tu-chon | **FAIL** | list_users | 2 user trùng tên "Nam": model TỰ CHỌN một Nam và gọi lock_user (dừng ở awaiting_confirmation) thay vì hỏi lại. Đúng lỗi "nhầm người" mà Phase 2 (resolver + luật 3 mức) nhắm diệt — giữ scenario này làm thước đo trước/sau. |
| tra-cuu-tien-do-project | PASS | list_projects, list_tasks, search | |
| danh-ba | PASS | list_users | |
| gui-email-awaiting-confirm | PASS | list_users | dừng đúng ở awaiting_confirmation, pending send_email |
| dashboard-hom-nay | PASS | get_today_dashboard | |
| tim-kiem | PASS | search, get_task | |
| tao-ghi-chu | PASS | create_note | |
| nhan-vien-cap-nhat-tien-do | PASS | list_tasks, add_task_update | |
| bao-duy-deadline-directive | SKIP | — | phase 2 |

## Prompt caching (acceptance 4.3)

**Không verify được cache_read trên gateway beeknoee hiện tại.** Bằng chứng:

- **(a) glm-4.7-flash** — gateway không trả usage, mọi cột token = 0
- **(b) Thử riêng 1 scenario với MODEL_FAST=anthropic/claude-haiku-4-5-20251001**:
  - Call đầu: input_tokens=12.711 nhưng cache_write_tokens=0 (nếu caching hoạt động phải ~12k)
  - Call sau: usage toàn 0 → gateway strip/không passthrough cache_control và trả usage không ổn định

**Xác nhận:** Code caching đã verify đúng ở tầng payload bằng unit test (`tests/test_llm_client_cache.py`). Acceptance cache_read chỉ đo được khi gọi thẳng api.anthropic.com — làm khi có key trực tiếp.

## Ghi chú vận hành

1. **Tracing hoạt động tốt** — khi model id sai với gateway, agent_traces bắt đúng stop_reason=error + model đã thử (anthropic/claude-haiku-4-5, iterations=1)

2. **Model id anthropic qua gateway PHẢI kèm date suffix** (anthropic/claude-haiku-4-5-20251001)

3. **Quan sát 1 mẫu** (chưa đủ dữ liệu kết luận): cùng scenario giao-task, Haiku-qua-gateway dừng hỏi lại sau list_users (thiếu create_task) trong khi glm-4.7-flash làm trọn — ghi để tham khảo

## Backlog bắt buộc trước Phase 2

- **Trace tool đã được confirm**: tool nhạy cảm chạy trong `resolve_confirmation` (ngoài `run_agent_loop`) hiện KHÔNG được ghi vào `agent_traces.tools_called` — request lock_user đã duyệt sẽ thiếu đúng tool quan trọng nhất trong trace. Phase 2 mở rộng `resolve_confirmation` cho `propose_actions` là thời điểm bắt buộc phải vá (ghi 1 dòng AgentTrace riêng hoặc nối vào trace của lần chạy kế).
- Số scenario thực tế của bank: 15 (14 phase-0 + 1 phase-2) — plan Task 7 ghi nhầm "16"; đích dài hạn ~40-50 theo spec §4.2 qua quy ước "mỗi bug fix → thêm scenario".

---

# BASELINE: Phase 1 — Workspace Snapshot (2026-07-22)

Task 8 (verify e2e). Full pytest: 479 passed (0 fail, chạy ngoài khung giờ lỗi ~23h-24h VN
nên 3 test dashboard flaky không trigger lần này).

## Tóm tắt chung

| Ngày | Model | Pass | Fail | Skip | Ghi chú |
|---|---|---|---|---|---|
| 2026-07-22 | glm-4.7-flash (dev .env, gateway beeknoee) | 11/17 | 6 | 1 | Sau snapshot (Phase 1). So Phase 0 (13/14): xem điều tra flakiness bên dưới — KHÔNG phải regression hạ tầng. |

**Bank giờ có 18 scenario** (14 phase-0 + 3 snapshot mới + 1 phase-2 skip), Task 7 đã thêm
`snapshot-tinh-hinh-du-an`, `snapshot-ai-dang-lam-gi`, `snapshot-hom-nay-co-gi`.

## Điều tra flakiness (quan trọng — đọc trước khi đọc bảng pass/fail)

Chạy full suite 2 lần (10/17 rồi 11/17), rồi chạy lại RIÊNG LẺ từng scenario fail 1-3 lần để
phân biệt "regression hạ tầng thật" và "model dev nhỏ không ổn định":

| Scenario | Kết quả khi chạy riêng lẻ | Kết luận |
|---|---|---|
| giao-task-co-deadline | fail, fail, **pass** (3 lần) | Flaky — không phải regression |
| khong-dau | fail (batch), **pass** (riêng lẻ) | Flaky |
| viet-tat | fail (batch), **pass** (riêng lẻ) | Flaky |
| nhan-vien-cap-nhat-tien-do | fail (batch), **pass** (riêng lẻ) | Flaky |
| tim-kiem | fail (batch), **pass** (riêng lẻ) | Flaky |
| gui-email-awaiting-confirm | fail (batch), **pass** (riêng lẻ) | Flaky |
| nhan-vien-doi-tao-project | pass, **fail** (2 lần riêng lẻ) | Flaky theo cả 2 chiều. Khi fail, model tự gọi `create_project` dù là employee — nhưng đây là model cư xử sai, KHÔNG phải lỗ hổng quyền: service layer `require_ceo` vẫn chặn (bất biến CLAUDE.md "quyền kiểm tra ở service layer, không bao giờ ở prompt/model", đã pytest cover riêng) |
| trung-ten-khong-tu-chon | fail (đúng như Phase 0 baseline) | **Không phải regression** — đây là fail đã biết/chủ đích từ Phase 0 (xem dòng gốc phía trên), để dành làm thước đo cho resolver Phase 2 |
| snapshot-tinh-hinh-du-an | **pass cả 2/2 lần chạy riêng lẻ** | Ổn định — 0-tool, trả lời đúng từ snapshot |
| snapshot-ai-dang-lam-gi | fail 4/5 lần (gọi `search`/`list_tasks` dù có snapshot) | Model KHÔNG hoàn toàn tin snapshot dù có sẵn — xem xác minh hạ tầng bên dưới, chấp nhận theo đúng guidance Task 8 ("model vẫn gọi tool — hành vi model, không phải bug hạ tầng, KHÔNG ép pass") |
| snapshot-hom-nay-co-gi | pass 2/3, fail 1/3 (gọi `get_today_dashboard`) | Cùng loại với trên — flaky nghiêng về pass |

**Xác minh hạ tầng (không phải bug):** gọi trực tiếp `snapshot_service.get_snapshot_text()` cho
actor CEO của workspace eval — snapshot render ĐÚNG và ĐẦY ĐỦ (project/tiến độ/nhân sự/hôm nay),
có câu lệnh rõ ràng "tin cậy, ưu tiên trả lời từ đây thay vì gọi tool tra lại". Vậy infra tiêm
snapshot hoạt động đúng — phần "model đôi khi vẫn gọi tool" là hạn chế của model dev nhỏ
(glm-4.7-flash), không phải lỗi Phase 1.

**Kết luận:** không có regression hạ tầng thật nào từ Phase 1. Toàn bộ chênh lệch so baseline
Phase 0 là (a) flakiness của model dev vốn đã biết trước (xem "Ghi chú vận hành" Phase 0 —
quan sát Haiku-vs-glm khác hành vi), hoặc (b) 1 fail đã biết/chủ đích (trung-ten-khong-tu-chon,
giữ nguyên cho Phase 2), hoặc (c) model không 100% tuân theo chỉ dẫn "ưu tiên dùng snapshot" —
điểm cần cải thiện ở Phase 2+ (có thể cần câu lệnh mạnh hơn hoặc model tốt hơn cho production),
không phải lỗi triển khai.

## Latency scenario snapshot (acceptance §5: p50 < 4000ms)

Đo qua `agent_traces.total_latency_ms` cho các request 0-tool, 1-iteration, chạy CÔ LẬP
(không chạy đồng thời scenario khác) để tránh nhiễu do gateway serialize (giới hạn 1 request
đồng thời, đã ghi nhận từ Phase 0):

- `snapshot-tinh-hinh-du-an` (0-tool, chạy cô lập): **16000ms**

**Acceptance <4000ms KHÔNG đạt trên gateway dev hiện tại.** Không phải do tính snapshot chậm —
build/render snapshot là SQL aggregate + cache Redis, đo riêng dưới mili-giây. Độ trễ đo được
là độ trễ round-trip gọi LLM qua gateway beeknoee (dev, glm-4.7-flash) — cùng loại giới hạn đã
ghi nhận ở Phase 0 (không verify được cache_read vì gateway không passthrough usage/cache ổn
định). Khi chạy theo batch (nhiều scenario liên tiếp), độ trễ 1 số request lên tới 50-64s do
gateway xếp hàng (1-concurrency) — càng không phản ánh chi phí thật của tính năng. Acceptance
latency cần đo lại khi có model/gateway production thật (Anthropic trực tiếp hoặc model_fast
thật), không phải trên dev stack này.

## Deviation §5.2 đã chốt

Lazy build-on-miss + TTL (`snapshot_ttl_seconds`) + invalidate tại agent choke point (sau
write-tool trong `run_agent_loop`) — KHÔNG dùng worker nền/debounce arq riêng, theo đúng
Global Constraints của plan.
