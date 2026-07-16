# Thiết kế FE (+ 1 sửa BE nhỏ) — Màn hình Team (khóa/mở/nghỉ việc/đổi vai trò)

**Ngày:** 2026-07-16 · **Trạng thái:** Đã duyệt qua brainstorming · **Spec BE liên quan:** offboarding (2026-07-14), role-manager-change (2026-07-15) — API đã có sẵn, spec này chỉ thêm UI + 1 field lộ ra qua `UserOut`.

Lấp phần FE còn thiếu cho 4 hành động quản trị nhân sự đã có BE từ trước nhưng chưa có màn hình nào: khóa/mở tài khoản, cho nghỉ việc, đổi vai trò/quản lý. Không có tiền lệ FE nào (chưa từng có màn danh sách người dùng) — dựng từ đầu.

---

## 1. Phạm vi & Ranh giới

**Trong phạm vi:**
- 1 sửa BE nhỏ: `UserOut` (`backend/app/schemas.py`) thêm `manager_id`, `status` (dữ liệu đã có trên model `User`, chỉ chưa lộ qua API).
- 1 API module mới `frontend/src/api/team.ts`.
- 2 màn hình mới: `team.tsx` (danh sách) + `team/[id].tsx` (chi tiết + 4 hành động).
- Entry point "Team" trong Settings — **CEO-only toàn bộ** (cả list lẫn detail lẫn 4 hành động), không có chế độ xem hạn chế cho manager/employee.
- Ô chọn "người kế nhiệm" luôn có sẵn (tùy chọn) trong form nghỉ việc/đổi vai trò — không gọi API kiểm tra trước, dựa vào lỗi `422 successor_required` từ BE để nhắc CEO chọn.

**Ngoài phạm vi (cố ý, YAGNI):**
- Không tìm kiếm/lọc trong danh sách người (công ty nhỏ).
- Không tạo tài khoản mới từ màn này (đã có "Mã mời" trong Settings).
- Không sửa `full_name`/`email` (không có endpoint).
- Không có chế độ xem cho manager/employee (khác quyết định ban đầu về "danh bạ cho mọi người" — đã chốt CEO-only để đơn giản).

---

## 2. Sửa BE — `backend/app/schemas.py`

```python
class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_root: bool
    manager_id: uuid.UUID | None
    status: str

    model_config = {"from_attributes": True}
```

Không cần sửa `backend/app/api/users.py` hay service nào — `response_model=UserOut`/`response_model=list[UserOut]` tự serialize thêm 2 field từ ORM object (`from_attributes=True` đã bật sẵn). Chạy lại `python scripts/export_openapi.py` sau khi sửa (đổi contract).

---

## 3. API module — `frontend/src/api/team.ts`

```ts
import { apiFetch } from "./client";

export type TeamUser = {
  id: string;
  email: string;
  full_name: string;
  role: "ceo" | "manager" | "employee";
  is_root: boolean;
  manager_id: string | null;
  status: "active" | "locked";
};

export type OffboardResult = {
  locked: boolean;
  successor_id: string | null;
  tasks_reassigned: number;
  projects_reassigned: number;
  reports_reassigned: number;
};

export type ChangeRoleResult = {
  role: string;
  manager_id: string | null;
  successor_id: string | null;
  reports_reassigned: number;
  projects_reassigned: number;
};

export const listUsers = () => apiFetch<TeamUser[]>("/api/v1/users");

export const lockUser = (id: string) =>
  apiFetch<void>(`/api/v1/users/${id}/lock`, { method: "POST" });

export const unlockUser = (id: string) =>
  apiFetch<void>(`/api/v1/users/${id}/unlock`, { method: "POST" });

export const offboardUser = (id: string, successorId?: string) =>
  apiFetch<OffboardResult>(`/api/v1/users/${id}/offboard`, {
    method: "POST",
    body: successorId ? { successor_id: successorId } : {},
  });

export const changeRole = (
  id: string,
  body: { new_role?: string; new_manager_id?: string; successor_id?: string },
) => apiFetch<ChangeRoleResult>(`/api/v1/users/${id}/change-role`, { method: "POST", body });
```

---

## 4. Màn danh sách — `frontend/app/(main)/team.tsx`

Route ẩn (giống `report-schedules.tsx`/`audit-log.tsx`), entry point trong `settings.tsx` gate bằng `user?.role === "ceo"` (mẫu y hệt card "Nhật ký thay đổi" vừa thêm, không kèm điều kiện gói dịch vụ).

4 trạng thái chuẩn. Mỗi dòng: `full_name` + nhãn vai trò tiếng Việt (khớp cách `settings.tsx` đang dịch: "CEO"/"Manager"/"Nhân viên") + badge nhỏ màu `colors.danger` "Đã khóa" nếu `status === "locked"`. Cả dòng là `TouchableOpacity` → `router.push(`/team/${u.id}`)`.

---

## 5. Màn chi tiết — `frontend/app/(main)/team/[id].tsx`

**Data:** gọi `listUsers()` (không có endpoint `GET /users/{id}` riêng), tìm người khớp `id` trong route param — dữ liệu nhỏ, không cần endpoint mới, giống tinh thần tái dùng đã áp dụng cho `audit-log`/`report-schedules`. Nếu không tìm thấy (id lạ/đã bị xóa) → hiện lỗi chung.

**Bố cục:** card thông tin (tên, email, vai trò, "Báo cáo cho: {tên manager}" nếu `manager_id` khớp 1 người trong danh sách đã tải, trạng thái) + card "Hành động":

- **Khóa/Mở tài khoản:** 1 nút duy nhất đổi nhãn theo `status` hiện tại ("Khóa tài khoản" nếu `active`, "Mở khóa" nếu `locked`) → `Alert.alert` xác nhận → gọi `lockUser`/`unlockUser` → refetch danh sách người (để cập nhật `status` mới) → hiện lại đúng trạng thái.
- **Cho nghỉ việc:** nút "Cho nghỉ việc" → mở rộng 1 panel con: ô chọn "Người kế nhiệm (nếu cần)" (tùy chọn — xem mục 6) + nút "Xác nhận nghỉ việc" (có `Alert.alert` xác nhận trước khi gọi API, vì đây là hành động nặng — khóa tài khoản + bàn giao). Lỗi hiện qua `ErrorText` ngay trong panel (không phải `Alert`, vì panel đã có state riêng, khác hành động tức thời như khóa/mở).
- **Đổi vai trò/quản lý:** nút "Đổi vai trò" → mở rộng 1 panel con:
  - Chọn vai trò mới: 3 nút dạng chip (CEO / Manager / Nhân viên), mặc định chọn sẵn vai trò hiện tại.
  - Nếu chọn "Nhân viên": hiện thêm ô chọn "Quản lý" (bắt buộc chọn trong nhóm Manager — theo ràng buộc BE `employee_requires_manager`).
  - Ô chọn "Người kế nhiệm (nếu cần)" — luôn hiện, tùy chọn (giống nghỉ việc).
  - Nút "Xác nhận" → gọi `changeRole` → lỗi hiện qua `ErrorText` trong panel.

**Không tự validate phía FE các ràng buộc BE đã có** (vd chỉ root mới đổi được CEO, employee bắt buộc có manager) — cứ gọi API, hiện đúng message lỗi BE trả về (giống cách các plan trước xử lý lỗi domain, không viết lại logic quyền/validate ở FE).

---

## 6. Component picker dùng chung — chọn 1 người từ danh sách

Không có sẵn dropdown/select component nào trong `src/ui/`. Thiết kế nhẹ, tái dùng cho cả "Quản lý" lẫn "Người kế nhiệm": 1 field dạng `TouchableOpacity` hiện tên đang chọn (hoặc "Chưa chọn") → bấm vào mở 1 danh sách cuộn bên dưới field đó (không phải modal riêng, giống cách `DateTimePicker` ở `audit-log.tsx` mở/đóng theo state `boolean`) → bấm 1 tên → đóng danh sách, set giá trị.

```tsx
function PersonPicker({
  label,
  people,
  value,
  onChange,
}: {
  label: string;
  people: TeamUser[];
  value: string | null;
  onChange: (id: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const selected = people.find((p) => p.id === value);
  return (
    <View>
      <TouchableOpacity onPress={() => setOpen((o) => !o)}>
        <Text style={{ color: colors.primary }}>
          {label}: {selected ? selected.full_name : "Chưa chọn"}
        </Text>
      </TouchableOpacity>
      {open && (
        <View style={styles.pickerList}>
          {people.map((p) => (
            <TouchableOpacity
              key={p.id}
              onPress={() => {
                onChange(p.id);
                setOpen(false);
              }}
              style={styles.pickerRow}
            >
              <Text>{p.full_name}</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
    </View>
  );
}
```

- "Quản lý": `people` = danh sách lọc `role === "manager"`.
- "Người kế nhiệm": `people` = danh sách lọc bỏ chính người đang xem (`id !== target.id`) và bỏ người đang `status === "locked"` (khớp ràng buộc BE `invalid_successor` khi successor đã bị khóa).

---

## 7. Xử lý lỗi (tổng hợp, tái dùng message BE nguyên văn qua `ErrorText`/`Alert`)

| Hành động | Lỗi có thể gặp | Cách hiện |
|---|---|---|
| Khóa/mở | 403/404 (hiếm, vd root CEO) | `Alert.alert` |
| Nghỉ việc | `422 successor_required`, `422 invalid_successor`, 403/404 | `ErrorText` trong panel |
| Đổi vai trò | `422 employee_requires_manager`, `422 invalid_manager`, `422 successor_required`, `422 no_change_requested`, `403 only_root_can_change_ceo`, `403 cannot_change_root_ceo` | `ErrorText` trong panel |

Không map riêng từng mã lỗi sang tiếng Việt cụ thể (khác attachment/audit — ở đây message BE trả về đã là chuỗi kỹ thuật như `"employee_requires_manager"`) — chấp nhận hiện nguyên message thô qua `ErrorText`, giống cách `report-schedules.tsx` đang xử lý lỗi chung. CEO là người dùng kỹ thuật đủ hiểu ngữ cảnh (khác end-user), không cần bản dịch đẹp cho mỗi mã lỗi.

---

## 8. Testing / Verification

Không có test framework FE — `npx tsc --noEmit` (0 lỗi) + chạy tay:
- CEO vào Settings → "Team" → thấy danh sách toàn công ty.
- Bấm 1 người → thấy chi tiết, đúng "Báo cáo cho".
- Khóa 1 người → badge "Đã khóa" xuất hiện đúng; mở lại → badge biến mất.
- Đổi vai trò 1 nhân viên thành manager → thành công, quay lại danh sách thấy nhãn vai trò đổi đúng.
- Thử đổi vai trò 1 manager đang có report mà KHÔNG chọn người kế nhiệm → thấy lỗi `successor_required` hiện trong panel.
- Cho 1 người nghỉ việc → thành công, badge "Đã khóa" xuất hiện.
- Manager/employee đăng nhập → Settings → KHÔNG thấy card "Team".

---

## Self-review (đã chạy)

- **Placeholder scan:** không có TBD; component picker, bảng lỗi, cấu trúc panel đã chốt cụ thể.
- **Nhất quán nội bộ:** gate CEO-only 1 chỗ duy nhất (Settings entry point), không viết logic quyền mới ở FE — mọi validate dựa vào BE trả lỗi. `PersonPicker` dùng chung 1 component cho cả 2 nhu cầu (quản lý/kế nhiệm), tránh trùng lặp code.
- **Phạm vi:** đủ cho 1 implementation plan — ước lượng 4-5 task (BE UserOut + API module, màn danh sách, chi tiết + khóa/mở, panel nghỉ việc, panel đổi vai trò). Không cần tách spec riêng nữa (khác quyết định trước đó tách audit-log ra) vì tất cả đều xoay quanh đúng 1 màn "quản lý 1 người", không độc lập được với nhau.
- **Ambiguity check:** đã chốt "CEO-only toàn bộ không có chế độ xem hạn chế", "luôn có sẵn ô kế nhiệm không gọi API kiểm tra trước", "không validate lại ràng buộc BE ở FE, chỉ hiện message thô" — không còn chỗ hiểu 2 nghĩa.
