# FE nhật ký thay đổi (audit log) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans hoặc superpowers:subagent-driven-development để thực thi plan này task-by-task. Checkbox (`- [ ]`) để tracking.

**Goal:** CEO vào Settings → "Nhật ký thay đổi" → thấy timeline hoạt động công ty (200 dòng gần nhất), lọc được theo khoảng ngày.

**Architecture:** 1 file API mới (`src/api/audit.ts`) gọi thẳng `GET /api/v1/audit-events` đã có sẵn ở BE. 1 màn hình mới `app/(main)/audit-log.tsx` — route ẩn (giống `report-schedules.tsx`), vào qua 1 card mới trong Settings gate bằng `user?.role === "ceo"`. Lọc ngày dùng `@react-native-community/datetimepicker` (package mới).

**Tech Stack:** Expo SDK 57 (`~57.0.4`), expo-router, React Native `StyleSheet`. Thêm 1 dependency mới: `@react-native-community/datetimepicker`.

**Spec thiết kế:** [docs/superpowers/specs/2026-07-16-audit-log-fe-design.md](../specs/2026-07-16-audit-log-fe-design.md)
**Spec BE liên quan:** [docs/superpowers/specs/2026-07-16-audit-log-design.md](../specs/2026-07-16-audit-log-design.md)

## Global Constraints (frontend/AGENTS.md, frontend/DESIGN.md, spec FE)

- Expo SDK `~57.0.4` — tra đúng docs bản 57 cho `@react-native-community/datetimepicker` trước khi viết code liên quan (theo `frontend/AGENTS.md`: "Expo HAS CHANGED").
- Mọi màn hình dùng token từ `src/ui/theme.ts` (`colors`, `spacing`, `radius`, `type`) — không hardcode hex/số spacing lẻ.
- Đủ 4 trạng thái bắt buộc mỗi khối dữ liệu: loading, empty, error, success.
- Gate CEO-only CHỈ bằng `user?.role === "ceo"` tại entry point trong `settings.tsx` — KHÔNG kèm điều kiện `sub?.plan === "advanced"` (khác `report-schedules`, vì BE audit log không giới hạn theo gói dịch vụ). Bản thân `audit-log.tsx` không tự kiểm tra quyền gì — dựa vào BE 403 làm lưới an toàn thứ 2, hiển thị qua `ErrorText` như lỗi thường (đúng convention FE hiện tại, không có "not allowed" UI riêng ở đâu).
- Không lọc theo loại sự kiện/người, không tap-to-detail trên dòng event, không Team screen (khóa/mở/offboard/đổi vai trò) — ngoài phạm vi plan này.
- FE hiện không có test suite — xác minh bằng `npx tsc --noEmit` (0 lỗi) sau mỗi task, thay cho unit test.

---

### Task 1: API layer — `frontend/src/api/audit.ts`

**Files:**
- Create: `frontend/src/api/audit.ts`

**Interfaces:**
- Produces: `type AuditEvent = {type, actor_id, actor_name, summary, created_at, target_user_id?, target_name?}`, `listAuditEvents(dateFrom?: string, dateTo?: string) => Promise<AuditEvent[]>`. Task 2 dùng cả 2.
- Consumes: `apiFetch<T>` từ `frontend/src/api/client.ts` (đã có, không sửa).

Không cần package mới cho task này.

- [ ] **Step 1: Tạo `frontend/src/api/audit.ts`**

```ts
import { apiFetch } from "./client";

export type AuditEvent = {
  type: "task_update" | "login" | "instruction_edit" | "skill_edit" | "account_event";
  actor_id: string;
  actor_name: string;
  summary: string;
  created_at: string;
  target_user_id?: string;
  target_name?: string;
};

export const listAuditEvents = (dateFrom?: string, dateTo?: string) => {
  const params = new URLSearchParams();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  const qs = params.toString();
  return apiFetch<AuditEvent[]>(`/api/v1/audit-events${qs ? `?${qs}` : ""}`);
};
```

- [ ] **Step 2: Xác minh bằng typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: không có output (0 lỗi) — file mới chỉ export type/function thuần.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/audit.ts
git commit -m "feat(fe): api layer nhat ky thay doi (audit log)"
```

---

### Task 2: Màn hình + date filter + entry point

**Files:**
- Create: `frontend/app/(main)/audit-log.tsx`
- Modify: `frontend/app/(main)/_layout.tsx`
- Modify: `frontend/app/(main)/settings.tsx`
- Modify: `frontend/package.json` (qua `npx expo install`, không tự sửa tay)

**Interfaces:**
- Consumes: `AuditEvent`, `listAuditEvents` (Task 1).

- [ ] **Step 1: Cài package `@react-native-community/datetimepicker`**

Run: `cd frontend && npx expo install @react-native-community/datetimepicker`
Expected: package xuất hiện trong `dependencies` của `frontend/package.json` với version khớp SDK 57 (Expo tự chọn).

- [ ] **Step 2: Tra docs Expo SDK 57 / package cho `@react-native-community/datetimepicker`**

Trước khi viết code, xem docs chính thức của package (https://github.com/react-native-datetimepicker/datetimepicker) để xác nhận chữ ký hiện hành khớp với những gì plan này giả định — plan này đã tra sẵn và ghi lại dưới đây:
  - `import DateTimePicker from "@react-native-community/datetimepicker";`
  - Props: `value: Date` (bắt buộc), `mode: "date"`, `onChange: (event, selectedDate?: Date) => void`.
  - `event.type` là `"set" | "dismissed"` — chỉ xử lý khi `"set"` và `selectedDate` tồn tại.
  - Cách hiện/ẩn: render có điều kiện (`{show && <DateTimePicker ... />}`) — KHÔNG dùng API imperative `DateTimePickerAndroid.open()` riêng cho Android trong plan này (giữ đơn giản, 1 pattern chung 2 platform).

Nếu version cài được (Step 1) có chữ ký khác (props đổi tên, `onChange` trả khác), sửa `audit-log.tsx` (Step 3) cho khớp — không đổi phần còn lại.

- [ ] **Step 3: Tạo `frontend/app/(main)/audit-log.tsx`**

```tsx
import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import DateTimePicker from "@react-native-community/datetimepicker";
import { AuditEvent, listAuditEvents } from "../../src/api/audit";
import { ErrorText } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";

const TYPE_ICON: Record<AuditEvent["type"], string> = {
  task_update: "📋",
  login: "🔐",
  instruction_edit: "🧠",
  skill_edit: "🧠",
  account_event: "👤",
};

function fmtDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function AuditEventRow({ e }: { e: AuditEvent }) {
  return (
    <View style={styles.row}>
      <Text style={{ fontSize: 18 }}>{TYPE_ICON[e.type]}</Text>
      <View style={{ flex: 1 }}>
        <Text style={type.body}>{e.summary}</Text>
        <Text style={{ color: colors.textSecondary }}>
          bởi {e.actor_name} · {new Date(e.created_at).toLocaleString("vi-VN")}
          {e.type === "account_event" && e.target_name ? ` → ${e.target_name}` : ""}
        </Text>
      </View>
    </View>
  );
}

export default function AuditLog() {
  const [dateFrom, setDateFrom] = useState<Date | null>(null);
  const [dateTo, setDateTo] = useState<Date | null>(null);
  const [showFromPicker, setShowFromPicker] = useState(false);
  const [showToPicker, setShowToPicker] = useState(false);
  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    listAuditEvents(dateFrom ? fmtDate(dateFrom) : undefined, dateTo ? fmtDate(dateTo) : undefined)
      .then(setEvents)
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, [dateFrom, dateTo]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
    >
      <View style={styles.card}>
        <View style={styles.filterRow}>
          <TouchableOpacity onPress={() => setShowFromPicker(true)}>
            <Text style={{ color: colors.primary }}>
              Từ ngày: {dateFrom ? fmtDate(dateFrom) : "Chưa chọn"}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setShowToPicker(true)}>
            <Text style={{ color: colors.primary }}>
              Đến ngày: {dateTo ? fmtDate(dateTo) : "Chưa chọn"}
            </Text>
          </TouchableOpacity>
        </View>
        {(dateFrom || dateTo) && (
          <TouchableOpacity
            onPress={() => {
              setDateFrom(null);
              setDateTo(null);
            }}
          >
            <Text style={{ color: colors.danger, marginTop: spacing.sm }}>Xóa lọc</Text>
          </TouchableOpacity>
        )}
      </View>
      {showFromPicker && (
        <DateTimePicker
          value={dateFrom ?? new Date()}
          mode="date"
          onChange={(event, selectedDate) => {
            setShowFromPicker(false);
            if (event.type === "set" && selectedDate) setDateFrom(selectedDate);
          }}
        />
      )}
      {showToPicker && (
        <DateTimePicker
          value={dateTo ?? new Date()}
          mode="date"
          onChange={(event, selectedDate) => {
            setShowToPicker(false);
            if (event.type === "set" && selectedDate) setDateTo(selectedDate);
          }}
        />
      )}
      {events === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {events?.length === 0 && (
        <Text style={{ color: colors.textMuted }}>
          {dateFrom || dateTo ? "Không có hoạt động nào trong khoảng thời gian này" : "Chưa có hoạt động nào"}
        </Text>
      )}
      {events && events.length > 0 && (
        <View style={styles.card}>
          {events.map((e, i) => (
            <AuditEventRow key={`${e.type}-${e.actor_id}-${e.created_at}-${i}`} e={e} />
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg },
  filterRow: { flexDirection: "row", justifyContent: "space-between" },
  row: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
});
```

- [ ] **Step 4: Đăng ký route ẩn trong `frontend/app/(main)/_layout.tsx`**

Sửa file — thêm 1 dòng ngay sau `report-schedules` (dòng 39 hiện tại):

```tsx
      <Tabs.Screen name="tasks/[id]" options={{ href: null }} />
      <Tabs.Screen name="report-schedules" options={{ href: null }} />
      <Tabs.Screen name="audit-log" options={{ href: null }} />
```

(2 dòng đầu giữ nguyên, chỉ để bạn thấy đúng vị trí chèn dòng thứ 3.)

- [ ] **Step 5: Thêm entry point trong `frontend/app/(main)/settings.tsx`**

Sửa file — thêm 1 card mới ngay sau khối `report-schedules` (dòng 45-50 hiện tại):

```tsx
      {user?.role === "ceo" && sub?.plan === "advanced" && (
        <TouchableOpacity style={styles.card} onPress={() => router.push("/report-schedules")}>
          <Text style={styles.title}>📅 Báo cáo định kỳ</Text>
          <Text style={{ color: colors.textSecondary }}>Xem và hủy lịch gửi báo cáo tự động</Text>
        </TouchableOpacity>
      )}
      {user?.role === "ceo" && (
        <TouchableOpacity style={styles.card} onPress={() => router.push("/audit-log")}>
          <Text style={styles.title}>📜 Nhật ký thay đổi</Text>
          <Text style={{ color: colors.textSecondary }}>Xem lịch sử hoạt động của công ty</Text>
        </TouchableOpacity>
      )}
```

(Khối `report-schedules` giữ nguyên không đổi — chỉ thêm khối `audit-log` mới ngay sau. Lưu ý card mới CHỈ gate bằng `user?.role === "ceo"`, KHÔNG kèm `sub?.plan === "advanced"` như khối phía trên.)

- [ ] **Step 6: Xác minh bằng typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: không có output (0 lỗi).

- [ ] **Step 7: Commit**

```bash
git add frontend/app/\(main\)/audit-log.tsx frontend/app/\(main\)/_layout.tsx frontend/app/\(main\)/settings.tsx frontend/package.json frontend/package-lock.json
git commit -m "feat(fe): man hinh nhat ky thay doi + loc theo ngay + entry point Settings"
```

---

## Ghi chú

- Không có test tự động cho các task này (FE chưa có hạ tầng test) — `npx tsc --noEmit` là bước xác minh duy nhất bắt buộc agent chạy. Xác minh bằng mắt qua Expo dev server (`npm run start` từ `frontend/`) nên làm thủ công sau khi cả 2 task xong:
  - Đăng nhập CEO → Settings → thấy card "Nhật ký thay đổi" → bấm vào → thấy danh sách (hoặc empty state nếu công ty mới chưa có hoạt động gì).
  - Chọn "Từ ngày"/"Đến ngày" → danh sách lọc lại đúng.
  - Bấm "Xóa lọc" → về lại danh sách đầy đủ.
  - Đăng nhập manager/employee → Settings → KHÔNG thấy card "Nhật ký thay đổi".
  - Không bắt buộc agent tự chạy simulator.
- Team screen (khóa/mở/offboard/đổi vai trò) — cố ý không nằm trong plan này, sẽ là spec+plan riêng sau (cần dựng màn hình danh sách người + chi tiết người từ đầu, và có thể cần sửa BE `UserOut` để trả thêm `manager_id`/`status`).
