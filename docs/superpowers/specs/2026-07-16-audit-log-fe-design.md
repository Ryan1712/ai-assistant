# Thiết kế FE — Nhật ký thay đổi (audit log)

**Ngày:** 2026-07-16 · **Trạng thái:** Đã duyệt qua brainstorming · **Spec BE liên quan:** [2026-07-16-audit-log-design.md](2026-07-16-audit-log-design.md)

BE (`GET /api/v1/audit-events?date_from&date_to`, CEO-only, tối đa 200 dòng) đã xong. Spec này lấp phần FE: 1 màn hình CEO xem timeline hoạt động công ty, có lọc theo khoảng ngày.

**Phạm vi quyết định:** Ban đầu gộp cùng FE cho offboard/đổi vai trò, nhưng khảo sát cho thấy 2 tính năng đó cần 1 màn hình "Team" hoàn toàn mới (list người + detail + hành động) — chưa tồn tại bất kỳ tiền lệ nào trong FE hiện tại (không có màn danh sách người dùng, không có UI khóa/mở tài khoản). Quyết định brainstorming: tách audit log FE thành spec độc lập, làm trước vì không phụ thuộc màn hình mới nào; Team screen (bao gồm khóa/mở/offboard/đổi vai trò) sẽ là spec riêng sau.

---

## 1. Phạm vi & Ranh giới

**Trong phạm vi:**
- 1 API module mới `frontend/src/api/audit.ts`.
- 1 màn hình mới `frontend/app/(main)/audit-log.tsx` — route ẩn (giống `report-schedules.tsx`), vào qua link trong Settings.
- Lọc theo khoảng ngày bằng date picker native (`@react-native-community/datetimepicker`, package mới), đúng theo quyết định brainstorming (không phải v1 tối giản không filter).
- Entry point trong `settings.tsx`, gate hiển thị bằng `user?.role === "ceo"` — **KHÔNG** gate thêm theo `sub?.plan === "advanced"` (khác `report-schedules` — audit log không giới hạn gói dịch vụ theo spec BE).

**Ngoài phạm vi (cố ý, YAGNI):**
- Không có "not allowed" UI riêng cho non-CEO — dựa hoàn toàn vào (a) entry point ẩn trong Settings, (b) BE tự trả 403 nếu truy cập trực tiếp, hiển thị qua `ErrorText` như lỗi thường. Đúng convention hiện tại của FE (không có màn hình nào tự xử lý 403 riêng).
- Không lọc theo loại sự kiện hay theo người — khớp giới hạn BE (BE cũng không hỗ trợ 2 filter này).
- Không có hành động nào trên dòng event (không tap-to-detail, không link sang task/user) — dữ liệu trả về không đủ để điều hướng có ý nghĩa (không có `task_id`, chỉ có `actor_id`/`target_user_id` dạng UUID thô).
- Team screen (khóa/mở/offboard/đổi vai trò) — spec riêng sau.

---

## 2. API module mới — `frontend/src/api/audit.ts`

Theo đúng pattern các API module khác (type phẳng + hàm mỏng bọc `apiFetch`):

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

`dateFrom`/`dateTo` là chuỗi `YYYY-MM-DD` (khớp kiểu `date` BE nhận qua query param) — màn hình tự convert từ `Date` object của date picker sang chuỗi này trước khi gọi (mục 4).

---

## 3. Package mới — `@react-native-community/datetimepicker`

Cài bằng `npx expo install @react-native-community/datetimepicker` (từ `frontend/`) để Expo tự chọn đúng version khớp SDK 57.

**API cơ bản** (tra lại docs chính thức tại thời điểm code để xác nhận version cài được không lệch — theo `frontend/AGENTS.md`):

```tsx
import DateTimePicker from "@react-native-community/datetimepicker";

// value: Date (bắt buộc), mode: "date", onChange: (event, selectedDate?: Date) => void
// event.type là "set" | "dismissed" — chỉ xử lý khi "set" và selectedDate tồn tại
```

**Cách hiện/ẩn:** dùng render có điều kiện (không dùng API imperative `DateTimePickerAndroid.open()` riêng cho Android — giữ đơn giản, 1 pattern chung cho cả 2 platform, chấp nhận UX Android hơi khác iOS 1 chút, phù hợp mức độ nội bộ của tính năng này):

```tsx
const [showFromPicker, setShowFromPicker] = useState(false);
...
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
```

---

## 4. Màn hình `frontend/app/(main)/audit-log.tsx`

**Data flow:**
- Mount: `listAuditEvents()` không tham số → 200 dòng gần nhất.
- Đổi `dateFrom`/`dateTo` (qua picker) → tự động gọi lại `listAuditEvents(dateFrom, dateTo)` (không cần nút "Áp dụng" riêng).
- Nút "Xóa lọc" (chỉ hiện khi có ít nhất 1 trong 2 ngày đã chọn) → reset `dateFrom`/`dateTo` về `null`.

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
      {events === null && !error && <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />}
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

Ghi chú key: BE không trả `id` riêng cho mỗi event (dict gộp từ 5 nguồn, không có UUID chung) — dùng key tổng hợp `${type}-${actor_id}-${created_at}-${index}` cho `.map()`, đủ duy nhất trong 1 lần render (không cần ổn định qua re-render vì list luôn refetch toàn bộ, không patch từng phần tử).

---

## 5. Đăng ký route + entry point

**`frontend/app/(main)/_layout.tsx`** — thêm 1 dòng ngay sau `report-schedules` (dòng 39 hiện tại):

```tsx
      <Tabs.Screen name="tasks/[id]" options={{ href: null }} />
      <Tabs.Screen name="report-schedules" options={{ href: null }} />
      <Tabs.Screen name="audit-log" options={{ href: null }} />
```

**`frontend/app/(main)/settings.tsx`** — thêm 1 card mới ngay sau khối `report-schedules` (dòng 45-50 hiện tại), gate CHỈ bằng role (không kèm điều kiện gói dịch vụ):

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

---

## 6. Testing / Verification

Không có test framework trong dự án FE (đã xác nhận ở các plan FE trước) — verify bằng `tsc --noEmit` sạch sau mỗi bước + chạy tay trên Expo dev server:
- Đăng nhập CEO → vào Settings → thấy card "Nhật ký thay đổi" → bấm vào → thấy danh sách (hoặc empty state nếu công ty mới chưa có hoạt động).
- Chọn "Từ ngày"/"Đến ngày" → danh sách lọc lại đúng.
- Bấm "Xóa lọc" → về lại danh sách đầy đủ.
- Đăng nhập bằng tài khoản manager/employee → vào Settings → KHÔNG thấy card "Nhật ký thay đổi".
- (Tuỳ chọn, không bắt buộc) thử gọi trực tiếp route `/audit-log` bằng tài khoản non-CEO (qua deep link hoặc gõ URL trên web) → thấy lỗi 403 hiển thị qua `ErrorText`, không crash.

---

## Self-review (đã chạy)

- **Placeholder scan:** không có TBD; icon mapping, format ngày, cách gate quyền đã chốt cụ thể.
- **Nhất quán nội bộ:** gate CEO-only ở đúng 1 chỗ (Settings entry point) — không lặp logic quyền ở `audit-log.tsx`, đúng convention `report-schedules.tsx` đã có. Route ẩn đăng ký đúng vị trí, không xung đột tab hiện có.
- **Phạm vi:** đủ nhỏ cho 1 implementation plan — ước lượng 2 task (API module + package, màn hình + đăng ký route/entry point). Team screen (khóa/mở/offboard/đổi vai trò) cố ý tách ra ngoài, sẽ là spec riêng.
- **Ambiguity check:** đã chốt rõ "route ẩn không phải tab mới", "gate chỉ theo role không theo gói dịch vụ (khác report-schedules)", "không tap-to-detail trên dòng event", "date picker dùng conditional-render chung 1 pattern cho cả 2 platform (không dùng API imperative riêng Android)" — không còn chỗ hiểu 2 nghĩa.
