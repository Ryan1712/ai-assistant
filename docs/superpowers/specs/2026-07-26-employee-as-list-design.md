# Nhân viên = tên trong danh sách công ty (bỏ tài khoản/mời)

**Ngày:** 2026-07-26
**Trạng thái:** Đã duyệt hướng, chờ review spec → writing-plans

## 1. Bối cảnh & quyết định

Product owner (CEO, solo dev) chốt: **chỉ CEO đăng nhập dùng app**. Mọi người khác trong công ty
chỉ là **record để gán việc** — một cái tên (kèm email tùy chọn), KHÔNG tài khoản, KHÔNG đăng nhập,
KHÔNG mời, KHÔNG mã kích hoạt, KHÔNG vai trò để chọn.

Lỗi cụ thể đang gặp: khi CEO giao việc cho người chưa có trong danh sách (vd "Duy Linh"), AI trả lời
*"Duy Linh chưa có trong danh sách nhân viên công ty. Bạn có muốn mời Duy Linh vào hệ thống trước
không?"*. Nguyên nhân gốc: công cụ `create_employee` mà AI dùng bản chất là **tạo tài khoản + sinh
mã kích hoạt**; mô tả và kết quả của nó đầy chữ "tạo tài khoản / mời vào làm / mã kích hoạt / mở app
kích hoạt" → model diễn đạt lại thành "mời vào hệ thống". Sửa câu chữ ở resolver (commit c7d4639)
không đủ vì bản thân công cụ vẫn mang mô hình "tài khoản".

Quyết định người dùng (qua AskUserQuestion, 2026-07-26):
- Thêm nhân viên: **tên bắt buộc + email tùy chọn** (không quản lý, không vai trò, không mã kích hoạt).
- Manager: **bỏ luôn** — chỉ CEO đăng nhập; manager (nếu có) cũng chỉ là tên trong danh sách.

## 2. Mô hình mới

- **CEO**: tạo qua `signup_workspace` (email + mật khẩu + `is_root`, role `ceo`) — KHÔNG đổi. Đăng
  nhập bình thường.
- **Người trong công ty (nhân viên)**: `User` record chỉ dùng làm assignee/recipient. `email` và
  `password_hash` cho phép rỗng. Không mật khẩu ⇒ không bao giờ đăng nhập được.
- `assign_task`/`TaskAssignee`/`Directive` giữ nguyên (đều tham chiếu `user_id`; `assign_task` vốn
  không kiểm tra role/status assignee — chỉ cùng workspace).

## 3. Thay đổi Backend

### 3.1 Data model + migration
- `User.email`: `nullable=True` (giữ `unique=True` — Postgres/SQLite cho nhiều NULL). CEO vẫn có email.
- `User.password_hash`: `nullable=True`. Người chỉ-có-tên không có mật khẩu.
- **Migration mới** (nối vào head hiện tại): `ALTER COLUMN email DROP NOT NULL`,
  `ALTER COLUMN password_hash DROP NOT NULL`. Không đổi dữ liệu cũ.
- **Defense-in-depth đăng nhập**: `login`/`rotate_refresh` phải từ chối user có `password_hash IS NULL`
  (không chỉ dựa "bcrypt fail"), đảm bảo record chỉ-tên tuyệt đối không đăng nhập được.

### 3.2 Service: `create_employee` → `add_employee`
Đổi hẳn `auth_service.create_employee` thành `add_employee` (không giữ alias tương thích — hành vi
khác hẳn, giữ 2 tên chỉ gây nhầm):
- Chữ ký: `add_employee(db, *, actor, full_name, email: str | None = None)`.
- Chỉ CEO (`require_ceo`). Bỏ tham số `role`, `manager_id`; bỏ guard manager/CEO-root/`employee_requires_manager`.
- Tạo `User(workspace_id, full_name, email=email or None, password_hash=None, role=Role.employee,
  status=UserStatus.active)`. **Không** tạo `Invite`, **không** sinh mã, **không** `expires_at`.
- Nếu có `email`: kiểm tra trùng trong workspace → 409 `email_taken`. Nếu không email: bỏ qua.
- Trả về `User` (chỉ record).
- `plans.enforce_limit(..., "members")`: GIỮ (xem §6 rủi ro — cân nhắc sau nếu danh sách tên lớn).

### 3.3 Công cụ AI (`app/agent/tools.py`)
- Đổi `create_employee` → `add_employee`:
  - `AddEmployeeToolIn`: `full_name: str`, `email: EmailStr | None = None`.
  - Mô tả: *"Thêm 1 người vào DANH SÁCH NHÂN VIÊN của công ty để giao việc (chỉ CEO). Chỉ cần tên;
    email là tùy chọn. Đây KHÔNG phải tạo tài khoản/đăng nhập — nhân viên không dùng app, chỉ CEO
    dùng. Dùng khi CEO nhắc tên người chưa có trong danh sách."* — tuyệt đối không dùng chữ
    mời/hệ thống/tài khoản/kích hoạt.
  - Handler trả `{"user_id", "full_name", "email", "note": "Đã thêm <tên> vào danh sách nhân viên
    công ty."}`.
- Cập nhật `TOOL_GROUPS["admin"]` (đổi tên), `SNAPSHOT_WRITE_TOOLS` (đổi tên; add_employee vẫn là
  write làm mới snapshot danh bạ).

### 3.4 System prompt (`app/agent/loop.py`)
- Ranh giới quyền: bỏ "tài khoản" khỏi danh sách việc CEO; mô tả rõ "nhân viên = danh sách tên để
  giao việc, không tài khoản".
- Quy tắc người-không-có-trong-danh-bạ (đã thêm ở c7d4639): giữ, chỉnh để nhất quán — khi CEO giao
  việc cho tên chưa có, AI **đề xuất thêm tên vào danh sách rồi giao việc** (gộp `add_employee` +
  `assign_task` trong 1 `propose_actions`), không hỏi vòng vo, tuyệt đối không nói "mời/hệ thống".

### 3.5 Resolver hint (`app/services/resolver_service.py`)
- `resolve_person` not_found: giữ "chưa có trong danh sách nhân viên"; đổi gợi ý sang "đề nghị thêm
  tên này vào danh sách (add_employee) nếu muốn giao việc" — bỏ mọi ngụ ý tài khoản.

### 3.6 Tắt luồng tài khoản/đăng nhập ngoài CEO (comment-out, giữ code theo quy ước dự án)
- REST: thêm route mới `POST /api/v1/employees` (`AddEmployeeIn{full_name, email?}` →
  `AddEmployeeOut{user_id, full_name, email}`) gọi `add_employee`. Comment-out route cũ
  `POST /api/v1/invites` + `CreateEmployeeIn/Out` (giữ code). FE chuyển sang gọi `/employees`.
- `POST /api/v1/auth/activate` + `activate_account` service: comment-out (không còn ai kích hoạt).
- `signup_with_code` / `POST /auth/signup-code`: đã tắt trước đó (commit 9175215) — giữ nguyên.
- Công cụ AI khóa/mở/nghỉ việc/đổi vai trò (`lock_user`, `unlock_user`, `offboard_user`,
  `change_user_role`): **giữ nguyên trong lần này** (xem §5) — chỉ bỏ khỏi mạch "thêm người".
- Export lại `openapi.json`.

## 4. Thay đổi Frontend
- `app/main/chat.tsx` `TOOL_LABELS`: `create_employee` → `add_employee` = "Thêm vào danh sách nhân viên".
- `app/auth/activate.tsx` + route `Activate` trong `AuthNavigator.tsx`/`types.ts`: comment-out (giữ file).
- `app/main/settings.tsx` / màn tạo nhân viên: rút gọn form còn **tên + email (tùy chọn)**; bỏ ô
  chọn vai trò/quản lý và phần hiển thị mã kích hoạt. Gọi endpoint `/employees` mới.
- Kiểm tra `AuthContext.tsx`/`login.tsx`: đảm bảo không còn link "kích hoạt/đăng ký bằng mã".

## 5. Ngoài phạm vi lần này (đề xuất gói riêng sau)
- Gỡ SÂU vai trò `manager` khỏi `permissions.py` (visibility/scoping), ma trận email
  (`email_service._check_matrix`), Directive, và các công cụ quản lý tài khoản (khóa/mở/nghỉ/đổi vai
  trò) + màn `team/detail.tsx`. Đụng nhiều file phân quyền + hàng loạt test (38 file dùng
  `Role.employee`, 16 dùng `Role.manager`) → rủi ro cao, tách riêng để giữ thay đổi này an toàn.
- Xem lại `plans.enforce_limit("members")` có nên đếm tên-không-đăng-nhập vào hạn mức seat không.

## 6. Rủi ro & cân nhắc
- **Migration nullable**: an toàn (chỉ nới lỏng ràng buộc). Phải nối `down_revision` vào head hiện tại.
- **Login an toàn**: bắt buộc test user `password_hash IS NULL` KHÔNG đăng nhập được (defense-in-depth).
- **Dữ liệu cũ**: nhân viên đã tạo trước đây (có email + status `pending` + Invite) vẫn hợp lệ; không
  cần migrate. Họ chỉ đơn giản không bao giờ kích hoạt nữa.
- **Member limit**: danh sách tên nhiều có thể chạm hạn mức gói — ghi nhận, quyết sau.
- **Test churn**: đổi tên tool + schema làm hỏng `test_create_employee.py`, `test_agent_tools_*`,
  fixture `_invite_and_join` (102 file dùng). Cần cập nhật fixture để tạo assignee kiểu mới (hoặc
  seed thẳng User) — đây là phần lớn công của plan.

## 7. Kiểm thử (TDD)
- `add_employee` service: tạo được với chỉ tên; với tên+email; email trùng → 409; không sinh mã/Invite;
  password_hash NULL.
- Login: user password_hash NULL → 401 (defense-in-depth).
- Công cụ `add_employee`: mô tả không chứa "mời/hệ thống/tài khoản/kích hoạt"; handler trả note đúng.
- System prompt: không còn "mời/hệ thống"; có "danh sách nhân viên".
- Luồng chat end-to-end (FakeLLM): CEO "giao việc cho <tên chưa có>" → propose_actions gồm
  add_employee + create_task + assign_task.
- Migration up/down chạy sạch.
