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
| khoa-acc-awaiting-confirm | PASS | awaiting_confirmation, pending lock_user đúng chủ đích | |
| nhan-vien-doi-tao-project | PASS | 0 tool — từ chối bằng lời | |
| khong-dau | PASS | create_task + assign_task | |
| viet-tat | PASS | create_task | |
| trung-ten-khong-tu-chon | **FAIL** | — | 2 user trùng tên "Nam": model TỰ CHỌN một Nam và gọi lock_user (dừng ở awaiting_confirmation) thay vì hỏi lại. Đúng lỗi "nhầm người" mà Phase 2 (resolver + luật 3 mức) nhắm diệt — giữ scenario này làm thước đo trước/sau. |
| tra-cuu-tien-do-project | PASS | list_projects, list_tasks, search | |
| danh-ba | PASS | list_users | |
| gui-email-awaiting-confirm | PASS | awaiting_confirmation, pending send_email | |
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
