# Thiết kế — FE liệt kê/xóa lịch báo cáo định kỳ

**Ngày:** 2026-07-14 · **Trạng thái:** Đã duyệt qua brainstorming · **BE liên quan:** [2026-07-13-plan9-scheduled-reports.md](../plans/2026-07-13-plan9-scheduled-reports.md) (REST `/api/v1/report-schedules` đã xong, BE) · **Spec chức năng:** [funtional-plan.md](../../../funtional-plan.md) §5.6 ("chat làm mọi việc"), §6.5, §10 (Giai đoạn 3)

Khép vòng Plan 9 (báo cáo định kỳ tự động): BE đã có đủ `POST/GET/DELETE /api/v1/report-schedules`, nhưng FE chưa có màn nào. Plan 9 tự ghi chú "FE UI liệt kê/xóa lịch có thể thêm sau nếu cần" — đây là phần đó.

---

## 1. Phạm vi & Ranh giới

**Trong phạm vi:**
- 1 card/link trong tab "Cài đặt" (`settings.tsx`), chỉ hiện khi `user.role === "ceo"` **và** `subscription.plan === "advanced"` — dẫn sang route `report-schedules` (ẩn khỏi tab bar, theo đúng pattern `href: null` đã dùng cho `tasks/[id]`).
- Màn `app/(main)/report-schedules.tsx`: **chỉ liệt kê + xóa**. Mỗi dòng hiện lịch chạy khi nào (thứ + giờ:phút, dịch sang tiếng Việt) + lần chạy kế tiếp (`next_run_at`) + trạng thái tạm dừng nếu `active === false`.
- Xóa: bấm nút "Xóa" → `Alert.alert` xác nhận → gọi API → xóa khỏi danh sách nếu thành công, hiện lỗi nếu thất bại.
- 1 file API mới `src/api/reportSchedules.ts` (chỉ `listReportSchedules`, `deleteReportSchedule` — không có hàm tạo).

**Ngoài phạm vi (cố ý, theo triết lý "chat làm mọi việc" — funtional-plan §5.6):**
- **Không có form tạo lịch trong app** — tạo lịch tiếp tục qua chat ("gửi báo cáo mỗi thứ 2 lúc 8h"), CEO đã dùng được ngay từ Plan 9 qua tool `create_report_schedule`. Xây form (weekday picker, giờ/phút, filter project/assignee/status, chọn người nhận) sẽ trùng lặp việc chat đã làm tốt, không có yêu cầu rõ ràng.
- **Không hiển thị filter (`project_id`/`assignee_id`/`status`) hay `recipient_id`** trong danh sách — đây là UUID thô, không có API resolve tên trong phạm vi màn này; hiện ra sẽ vô nghĩa với người dùng. CEO muốn xem chi tiết đầy đủ có thể hỏi chat (tool `list_report_schedules` đã trả đủ field).
- **Không sửa lịch (PATCH)** — BE chưa có endpoint sửa, chỉ có tạo/xem/xóa; không tự thêm.
- Không phân trang — danh sách lịch của 1 workspace luôn nhỏ (CEO tự tạo qua chat, không có nguồn sinh hàng loạt).

---

## 2. Điều hướng & entry point

### Sửa `app/(main)/settings.tsx`

Thêm 1 card mới, đặt sau card "Gói dịch vụ" hiện có, điều kiện hiện: `user?.role === "ceo" && sub?.plan === "advanced"` (dùng đúng 2 state `user`/`sub` đã có sẵn trong file, không fetch thêm):

```tsx
{user?.role === "ceo" && sub?.plan === "advanced" && (
  <TouchableOpacity style={styles.card} onPress={() => router.push("/report-schedules")}>
    <Text style={styles.title}>📅 Báo cáo định kỳ</Text>
    <Text style={{ color: colors.textSecondary }}>Xem và hủy lịch gửi báo cáo tự động</Text>
  </TouchableOpacity>
)}
```

Cần thêm `useRouter` từ `expo-router` vào import của `settings.tsx` (file này hiện chưa import `expo-router`).

### Route ẩn trong `_layout.tsx`

```tsx
<Tabs.Screen name="report-schedules" options={{ href: null }} />
```

Đặt cạnh dòng `tasks/[id]` đã có (cả 2 đều là route ẩn, không có `tabBarIcon`).

---

## 3. API layer — `src/api/reportSchedules.ts` (mới)

```ts
import { apiFetch } from "./client";

export type ReportSchedule = {
  id: string;
  weekday: number | null; // 0=Thứ Hai..6=Chủ Nhật, null=hàng ngày
  hour: number;
  minute: number;
  project_id: string | null;
  assignee_id: string | null;
  status: string | null;
  recipient_id: string;
  active: boolean;
  last_run_at: string | null;
  next_run_at: string;
  created_at: string;
};

export const listReportSchedules = () => apiFetch<ReportSchedule[]>("/api/v1/report-schedules");

export const deleteReportSchedule = (id: string) =>
  apiFetch<void>(`/api/v1/report-schedules/${id}`, { method: "DELETE" });
```

Field khớp chính xác `ReportScheduleOut` ở `backend/app/schemas.py:339-353` — kể cả field không hiển thị ở UI (`project_id`, `assignee_id`, `status`, `recipient_id`) vẫn giữ trong type cho đúng shape response, chỉ không render.

---

## 4. Màn `app/(main)/report-schedules.tsx`

- State: `schedules: ReportSchedule[] | null` (`null` = đang tải lần đầu), `error: string | null`.
- `useEffect` gọi `listReportSchedules()` khi mount.
- 4 trạng thái:
  - **Loading:** `schedules === null && !error` → `ActivityIndicator`.
  - **Empty:** `schedules?.length === 0` → "Chưa có lịch báo cáo nào — nhắn AI để đặt lịch, ví dụ 'gửi báo cáo mỗi sáng thứ 2 lúc 8h'".
  - **Error:** `error && <ErrorText error={error} />`.
  - **Success:** danh sách card, mỗi card 1 lịch.
- Dịch `weekday` sang nhãn tiếng Việt bằng 1 hàm thuần trong file:
  ```ts
  const WEEKDAY_LABEL = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"];
  function scheduleLabel(s: ReportSchedule) {
    const day = s.weekday === null ? "Hàng ngày" : WEEKDAY_LABEL[s.weekday];
    const time = `${String(s.hour).padStart(2, "0")}:${String(s.minute).padStart(2, "0")}`;
    return `${day}, ${time}`;
  }
  ```
- Mỗi dòng (theo pattern card của `today.tsx`):
  - Dòng chính: `scheduleLabel(s)` (`type.heading`).
  - Dòng phụ: "Kế tiếp: {format next_run_at theo vi-VN}" (`colors.textSecondary`).
  - Nếu `!s.active`: thêm dòng "Tạm dừng" màu `colors.textMuted`.
  - Nút "Xóa" (chữ, không icon-only nên không cần `accessibilityLabel` riêng — theo đúng quy tắc `DESIGN.md`) → `Alert.alert("Hủy lịch báo cáo?", "Sẽ không còn tự động gửi báo cáo theo lịch này nữa.", [{text: "Hủy", style: "cancel"}, {text: "Xóa", style: "destructive", onPress: confirmDelete}])`.
  - `confirmDelete`: gọi `deleteReportSchedule(s.id)`; thành công → `setSchedules(prev => prev!.filter(x => x.id !== s.id))`; thất bại → `setError(String(e?.message ?? e))` (giữ nguyên dòng trong danh sách).

---

## 5. Testing

Giống các plan FE trước — không có test framework trong repo (không Jest/RNTL), xác minh bằng `npx tsc --noEmit` (baseline hiện tại: 0 lỗi) sau mỗi task, không thêm hạ tầng test mới.

---

## Self-review (đã chạy)

- **Placeholder scan:** không có TBD; mọi quyết định (chỉ liệt kê+xóa không có form tạo, không hiện filter/recipient ID, Alert xác nhận trước khi xóa, entry point trong Settings) đã chốt qua brainstorming.
- **Nhất quán nội bộ:** field `ReportSchedule` khớp đúng `ReportScheduleOut` đã kiểm tra ở BE; dùng đúng component/token có sẵn (`ErrorText`, `theme.ts`), đúng pattern route ẩn đã dùng cho `tasks/[id]`, đúng convention lỗi `catch (e: any) => setError(String(e?.message ?? e))` đã dùng xuyên suốt các màn FE trước.
- **Phạm vi:** đủ nhỏ cho 1 implementation plan — ước lượng 2 task (API layer, màn liệt kê+xóa+entry point Settings). Không đụng BE, không thêm dependency.
- **Ambiguity check:** đã chốt rõ "không tạo lịch qua app", "không hiện filter/recipient", "có Alert xác nhận xóa" — không còn chỗ hiểu 2 nghĩa.
