# Resolve placeholder id trong propose_actions — thiết kế

**Ngày:** 2026-08-05
**Trạng thái:** Đã duyệt (brainstorm sau systematic-debugging), chờ viết
plan triển khai.

## Bối cảnh

PO feedback: *"Hay gặp lỗi tool tạo nhân viên, nhất là nhân viên chưa tồn
tại thì không tự động tạo"*. Điều tra bằng systematic-debugging (đọc code
thật, không đoán) xác nhận đây là **bug thật, root cause đã xác định
chắc chắn** — không phải hiểu nhầm của PO.

## Root cause

Khi CEO giao việc cho người **chưa có trong danh bạ** trong 1 câu (vd
"giao task X cho Duy Linh"), theo rule 3-mức trong system prompt
(`backend/app/agent/loop.py`, mức 2: *"phải SUY LUẬN đối tượng ... hoặc
gộp nhiều hành động trong 1 câu → gọi propose_actions NGAY"*), model gộp
`add_employee` + `assign_task` vào 1 bản nháp `propose_actions`. Vì lúc đề
xuất, người đó CHƯA tồn tại nên chưa có id thật — model tự bịa 1 chuỗi
placeholder tự nhiên (vd `"<id_Duy_Linh_sau_khi_them>"`) làm `user_id`
của action `assign_task`.

Khi CEO duyệt bản nháp, `_resolve_proposal`
(`backend/app/agent/loop.py:710-750`) chạy tuần tự từng action qua
`call_tool()`:
1. `add_employee` chạy thành công — Duy Linh được thêm thật, có `user_id`
   thật trong kết quả.
2. `assign_task` chạy với `tool_input={"user_id": "<id_Duy_Linh_sau_khi_them>", ...}`
   — **không có cơ chế nào thay chuỗi placeholder bằng id thật vừa tạo ở
   bước 1**. `AssignTaskToolIn.user_id: uuid.UUID`
   (`backend/app/agent/tools.py:125-127`) bắt buộc parse UUID hợp lệ →
   Pydantic validation fail ngay trong `call_tool()`
   (`tools.py:69-73`, nhánh `except Exception` → `{"error": "invalid_input", ...}`).

Kết quả: `outcome = "partially_completed"`. Nhân viên được tạo thật,
nhưng việc gán task — mục đích chính của yêu cầu — âm thầm fail. CEO phải
tự gán lại bằng tay. Model có báo lại theo rule đã có (dòng 147-151:
*"outcome khác 'completed' → PHẢI liệt kê rõ việc nào thất bại"*), nhưng
không có cơ chế tự sửa.

**Đây không phải case đơn lẻ.** Cùng pattern (action tạo-mới → action
dùng-id-của-nó) cũng xuất hiện ở luồng "dán nhiều task từ Excel"
(`loop.py:152-157`): `create_project` + N `create_task` + `assign_task`
trong 1 bản nháp — `create_task` cần `project_id` của `create_project`,
`assign_task` cần `task_id` của `create_task` tương ứng. Cùng lỗ hổng.

**Gap trong test:** `backend/tests/test_agent_add_employee_flow.py` chỉ
verify tới bước tạo `pending_action` (dòng 73-75), **không** verify bước
duyệt/thực thi thật — docstring dòng 22-29 tự thừa nhận: *"user_id trong
tool_input của action assign_task là giá trị placeholder ... điều này
chấp nhận được vì bản nháp propose_actions không bao giờ được thực thi
bằng call_tool() ... trong test này"*. Bug lọt qua vì test dừng đúng
trước điểm nó xảy ra.

**Mâu thuẫn nguồn hướng dẫn:** tool description `add_employee`
(`tools.py:442-444`) viết *"TUYỆT ĐỐI đừng gộp add_employee chung với
assign_task trong 1 bản nháp propose_actions, vì ... assign_task sẽ tham
chiếu 1 id không có thật và lỗi khi được duyệt"* — mâu thuẫn trực tiếp với
rule 3-mức bắt gộp. Rule 3-mức thắng trong thực tế (theo test hiện có),
nên description tool cần cập nhật lại cho khớp, không phải xóa khả năng
gộp.

## Thiết kế fix

### 1. Cú pháp placeholder chuẩn

`$result[N].<field>` — `N` là chỉ số action (0-based) trong cùng bản
nháp `actions` list, `<field>` là tên field thật trong `dict` trả về của
action đó (vd `$result[0].user_id`, `$result[0].id`). Không chuẩn hóa lại
tên field trả về của các tool hiện có (`add_employee` trả `user_id`,
`create_project`/`create_task` trả `id`) — giữ nguyên, cú pháp linh hoạt
theo field thật để tránh ảnh hưởng chỗ khác đang đọc đúng tên field cũ.

### 2. System prompt (`backend/app/agent/loop.py`)

Thêm rule mới, đặt cạnh 2 chỗ đang dạy pattern gộp action (dòng 124-129
rule 3-mức, và dòng 152-157 pattern "dán Excel"): khi 1 action trong bản
nháp cần id do action TRƯỚC nó (cùng bản nháp) sinh ra, PHẢI viết đúng cú
pháp `$result[N].<field>` — không tự bịa chuỗi tự nhiên như trước — với
`<field>` đúng tên tool đó thật trả về (model tra theo mô tả/kết quả tool
đã biết).

### 3. `_resolve_proposal` (`backend/app/agent/loop.py:710-750`)

Trước khi gọi `call_tool()` cho action thứ `i`, quét toàn bộ giá trị
string trong `tool_input` của nó (đệ quy 1 cấp, vì `tool_input` là flat
dict theo mọi action hiện có) tìm khớp pattern regex tường minh
`^\$result\[(\d+)\]\.(\w+)$`:

- Nếu khớp, lấy `N` = chỉ số action nguồn. Nếu `N >= i` (tham chiếu tới
  action chưa chạy hoặc chính nó) → coi là lỗi định dạng, skip action
  hiện tại với lỗi rõ ràng.
- Nếu action N đã chạy và **thành công** (`"error" not in results[N]["result"]`)
  và field tồn tại trong `results[N]["result"]` → thay giá trị placeholder
  bằng `str(results[N]["result"][field])`, tiếp tục gọi `call_tool()` bình
  thường với `tool_input` đã resolve.
- Nếu action N đã **fail**, hoặc field không tồn tại trong kết quả của N
  → **skip action hiện tại**, không gọi `call_tool()` (tránh side-effect
  ngoài ý muốn với input còn placeholder chưa resolve). Ghi kết quả lỗi
  rõ ràng: `{"error": "dependency_failed", "message": "Bỏ qua vì action
  phụ thuộc (#N: {display_text của action N}) thất bại"}`. Action này vẫn
  được tính vào `failed`, `outcome` vẫn tính đúng theo logic hiện có
  (`completed`/`partially_completed`/`failed`).

### 4. Tool description `add_employee` (`backend/app/agent/tools.py:434-445`)

Cập nhật đoạn cấm gộp (dòng 442-444) — đổi từ "TUYỆT ĐỐI đừng gộp" thành
hướng dẫn dùng đúng cú pháp `$result[N].user_id` khi cần gộp với
`assign_task` trong cùng bản nháp, nhất quán với rule mới ở system prompt.
Không xóa bỏ khả năng gộp — chỉ sửa để không còn mâu thuẫn với rule
3-mức.

## Test cần thêm (chi tiết ở plan triển khai)

1. `_resolve_proposal`: action 2 tham chiếu `$result[0].user_id` của
   action 1 (`add_employee`) → xác nhận `assign_task` chạy với đúng UUID
   thật đã tạo, `outcome = "completed"`.
2. Action nguồn (N) fail → xác nhận action phụ thuộc bị skip với lỗi
   `dependency_failed`, **không** gọi `call_tool()` thật cho action đó
   (verify bằng cách action đó không tạo side-effect nào trong DB).
3. Field không tồn tại trong result của action N (model viết sai tên
   field, vd `$result[0].id` khi tool N thật sự trả `user_id`) → skip
   tương tự, lỗi rõ ràng thay vì crash hoặc lỗi Pydantic khó hiểu.
4. Placeholder tham chiếu N >= i (tự tham chiếu hoặc tham chiếu tương
   lai) → skip với lỗi định dạng, không crash toàn bộ `_resolve_proposal`.
5. Backward compat: action không có placeholder nào (trường hợp phổ biến
   nhất, đã có test cũ) vẫn chạy y hệt như trước — không regression.
6. Cập nhật `test_agent_add_employee_flow.py`: đổi placeholder từ chuỗi
   tự nhiên `"<id_Duy_Linh_sau_khi_them>"` sang cú pháp mới
   `"$result[0].user_id"`, và **mở rộng test để verify cả bước duyệt
   thật** (gọi `resolve_confirmation`/`_resolve_proposal`, không chỉ dừng
   ở bước tạo draft) — đóng đúng gap đã khiến bug này lọt qua ban đầu.

## Ngoài phạm vi (chưa làm ở lần này)

- Không chuẩn hóa tên field trả về của các tool "tạo mới" hiện có (vẫn
  giữ `add_employee` trả `user_id`, `create_project`/`create_task` trả
  `id`) — đã cân nhắc và loại vì rủi ro ảnh hưởng chỗ khác đang đọc đúng
  tên field cũ, không cần thiết với cú pháp placeholder linh hoạt.
- Không hỗ trợ đệ quy sâu hơn 1 cấp trong `tool_input` (không có tool nào
  hiện tại có `tool_input` dạng nested object cần quét sâu).
- Không tự động retry action phụ thuộc sau khi action nguồn fail — chỉ
  báo lỗi rõ ràng để CEO tự quyết định làm lại.
