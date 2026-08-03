# Fix 3 bug agent chat (deep-analysis mất tin nhắn, bịa tên tool, lộ tường thuật lỗi) — thiết kế

**Ngày:** 2026-08-03
**Trạng thái:** Đã duyệt (brainstorm), chờ viết plan triển khai.

## Bối cảnh

User báo "AI chưa thông minh" kèm ảnh chụp 1 hội thoại thật trên app (giao việc
dự án 9Learning cho "Hiếu mafia"). Điều tra bằng cách tra trực tiếp
`chat_requests`/`messages`/`agent_traces` trên Postgres production (VPS,
khung giờ 2026-08-03 11:41–11:46 UTC — xem quy trình SSH ở
`project-vps-deployment` trong memory) xác nhận 3 bug độc lập, không phải suy
đoán từ ảnh:

1. **FE mất tin nhắn trả lời thật** khi WebSocket rớt kết nối đúng lúc
   route "deep" đang xử lý nền — user thấy "im lặng" dù backend đã xong.
2. **Model bịa tên tool** (`add_member`, `create_user` — tool thật là
   `add_employee`) dù mô tả tool trong code đã đầy đủ, rõ ràng.
3. **Model lộ tường thuật lỗi/retry kỹ thuật ra chat** ("Dự án đã tạo thành
   công! Tuy nhiên tôi gặp lỗi khi tạo task vì cần đúng ID...") — vi phạm rule
   sẵn có trong system prompt, là hệ quả trực tiếp của bug #2.

## Bug #1: FE mất tin nhắn khi WS rớt giữa lúc deep-analysis chạy nền

### Root cause (xác nhận bằng code + DB, không phải giả thuyết)

Route "deep" (`run_deep_ack_turn` → ghi ack message `is_ack=True` → enqueue
`run_deep_analysis` chạy nền bằng `model_smart`) là thiết kế **có chủ đích**
(Phase 4 §8.2): ack nhanh "~30 giây, tôi sẽ báo khi xong", xử lý thật ở
background, xong thì publish `token`/`request_done` qua WebSocket giống hệt
route "fast" (`backend/app/agent/loop.py` — `run_agent_loop` dùng chung cho
cả 2 route, không có nhánh nào bỏ qua publish khi `route="deep"`).

Trace thật của request test: ack (Haiku) 2.3s → `run_deep_analysis` (Sonnet)
5.8s → `status=done` lúc `11:41:58`, tức **~10 giây sau khi gửi** — nhanh hơn
nhiều so với "30 giây" đã hứa. Nhưng user vẫn hỏi lại "Tạo xong chưa?" lúc
`11:42:52` (54 giây **sau khi đã xong thật**) — vì màn hình chat không hiện
gì thêm ngoài dòng ack.

Nguyên nhân: `frontend/app/main/chat.tsx` — `refreshQueue` (dòng 235-264,
chạy khi WS `onReconnect`) chỉ bù đắp event bị lỡ cho trường hợp
`status=failed` (`missedFails`, dòng 246-260, có comment thừa nhận rủi ro WS
rớt ở dòng 228-229/238-239) — **không có nhánh tương tự cho `status=done`**.
Nếu WS rớt kết nối đúng lúc `run_deep_analysis` publish kết quả thật (xác
suất cao hơn hẳn route fast vì route deep chạy nền 10–800 giây, dễ trùng lúc
mạng mobile chập chờn), event `token`/`request_done` mất vĩnh viễn khỏi
UI dù `Message` đã nằm trong DB — không có cơ chế nào tự động bù lại.

### Fix

Thêm nhánh đối xứng `missedDone` trong `refreshQueue`
(`frontend/app/main/chat.tsx`):

- Theo dõi 1 `Set` mới `doneSeen.current` — đánh dấu `chat_request_id` mỗi
  khi WS event `request_done` thực sự tới (trong `onWsEvent`, nhánh
  `request_done` hiện có ở dòng 310-320).
- Trong `refreshQueue`, với mỗi request có `status === "done"` mà
  `watchedRequests.current.has(r.id)` (đã từng thấy nó chạy) nhưng
  **chưa** có trong `doneSeen.current`: gọi `listMessages(cid)`, lọc các
  `Message` có `chat_request_id === r.id`, convert qua `messagesToRows`
  (hàm helper có sẵn, dòng 146-173), nối vào cuối `rows` nếu `key` chưa tồn
  tại (dedupe), rồi đánh dấu request đó vào `doneSeen.current`.
- Cùng lúc, xoá dòng `stream-${r.id}` tạm (nếu còn) để không hiện trùng.

Không đổi API backend — chỉ dùng `listMessages` đã có sẵn
(`frontend/src/api/chat.ts:99-100`).

## Bug #2: Model bịa tên tool

### Vì sao không auto-redirect (đã cân nhắc và loại)

Thử nghiệm trigram similarity (`backend/app/services/fuzzy_match.py`, cùng
công thức dùng cho `resolve_person`/`resolve_task`) trên các cặp tên tool
thật cho kết quả **không an toàn để tự động redirect**:

| Cặp | Similarity |
|---|---|
| `add_member` ~ `add_employee` | 0.2 (dưới ngưỡng 0.3 đang dùng) |
| `create_user` ~ `add_employee` | 0.0 (không bắt được — đây là suy đoán ngữ nghĩa, không phải lỗi chính tả) |
| `delete_task` ~ `create_task` | 0.333 (**vượt ngưỡng**, nhưng 2 tool đối lập hoàn toàn) |
| `update_task` ~ `delete_task` | 0.333 (**vượt ngưỡng**, cũng đối lập) |

Trigram phù hợp cho tên người/task (chuỗi tự nhiên, lỗi chính tả gần đúng)
nhưng KHÔNG phù hợp cho tên tool (định danh kỹ thuật ngắn, dùng chung tiền
tố/hậu tố như `_task` dù ngữ nghĩa đối lập create/update/delete). Auto-
redirect theo similarity có rủi ro thật: biến 1 lệnh xóa thành 1 lệnh tạo.
→ Quyết định: **không tự động redirect tool_name sai.**

### Fix

1. **Cải thiện error hint** ở `call_tool()`
   (`backend/app/agent/tools.py:64-67`): khi `tool_name not in TOOLS`, tính
   `trigram_similarity` giữa tên gọi sai và toàn bộ key của `TOOLS`, liệt kê
   tối đa 3 tên tool thật có similarity cao nhất (chỉ để **hiển thị gợi ý
   trong hint cho model đọc**, không tự động gọi thay) — model vẫn phải chủ
   động chọn và gọi lại đúng tên ở vòng kế tiếp.
2. **Rule prompt bổ sung** trong `_build_system_prompt`
   (`backend/app/agent/loop.py`): nhấn mạnh tra đúng tên tool trong danh
   sách `tools` đã cấp trước khi gọi, không suy đoán/bịa tên tool tương tự
   dù nghe hợp lý về ngữ nghĩa.

## Bug #3: Lộ tường thuật lỗi/retry ra chat

Thêm rule prompt trong `_build_system_prompt`: khi 1 `tool_result` trả về có
field `error` (bất kỳ loại nào — `not_found`, `invalid_input`, `forbidden`,
`tool_failed`...) và model tự sửa/gọi lại ở vòng kế tiếp trong CÙNG 1 lượt
trả lời, **không kể lại việc vừa gặp lỗi** trong câu trả lời cuối cho
người dùng — chỉ báo kết quả cuối cùng, đúng như khi mọi thứ chạy trót lọt
ngay từ đầu. Đặt gần rule hiện có về cấm lộ tên tool/UUID kỹ thuật
(`loop.py` dòng 81-89) để nhất quán nhóm rule "không lộ chi tiết kỹ thuật
nội bộ".

**Giới hạn đã biết:** đây là fix ở tầng prompt, không đảm bảo tuyệt đối
(model vẫn có thể vi phạm) — giảm xác suất, không loại trừ. Tác dụng kết
hợp với bug #2 (giảm tần suất lỗi tool xảy ra) để giảm cơ hội bug #3 xuất
hiện, thay vì chỉ trông cậy vào việc model tự kiềm chế.

## Việc cần làm (tổng quan, chi tiết ở plan triển khai)

1. `frontend/app/main/chat.tsx`: thêm `doneSeen` ref, đánh dấu khi
   `request_done` tới, thêm nhánh `missedDone` trong `refreshQueue`.
2. `backend/app/agent/tools.py`: `call_tool()` — tính gợi ý tên tool gần
   đúng bằng `trigram_similarity` khi `tool_name not in TOOLS`.
3. `backend/app/agent/loop.py`: `_build_system_prompt` — thêm 2 rule (tra
   đúng tên tool trước khi gọi; không kể lại lỗi/retry nội bộ đã tự sửa).
4. Tests:
   - Backend: `call_tool` với tên tool sai gần giống (`add_member`) trả
     hint có gợi ý `add_employee`; tên tool sai xa (không match candidate
     nào) vẫn trả lỗi `not_found` như cũ, không crash.
   - Frontend: không có test suite tự động cho `chat.tsx` hiện tại (theo
     khảo sát repo) — verify bằng cách chạy thử luồng thật (đóng WS giữa
     chừng lúc route deep đang chạy, mở lại, xác nhận message xuất hiện)
     thay vì unit test.

## Ngoài phạm vi (chưa làm ở lần này)

- Không auto-redirect tool_name sai (rủi ro dữ liệu, đã loại — xem trên).
- Không thêm lớp hậu-kiểm LLM để validate output trước khi publish (chi phí
  thêm 1 LLM call/lượt, không tương xứng với mức độ nghiêm trọng hiện tại).
- Không đổi cơ chế push notification `deep_analysis_done` (đã hoạt động
  đúng thiết kế, không phải nguyên nhân bug #1).
- Không viết unit test tự động cho `chat.tsx` nói chung (ngoài phạm vi bug
  này) — chỉ verify thủ công nhánh `missedDone` mới thêm.
