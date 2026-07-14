# FE liệt kê/xóa lịch báo cáo định kỳ — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (recommended) hoặc superpowers:executing-plans để thực thi plan này task-by-task. Checkbox (`- [ ]`) để tracking.

**Goal:** CEO (gói Advanced) mở tab Cài đặt, bấm vào "📅 Báo cáo định kỳ", xem danh sách lịch báo cáo đang có, xóa được lịch không cần nữa. Tạo lịch mới vẫn qua chat (đã có từ Plan 9).

**Architecture:** 1 file API mới (`src/api/reportSchedules.ts`) gọi `GET`/`DELETE /api/v1/report-schedules` đã có sẵn ở BE. 1 route ẩn `app/(main)/report-schedules.tsx` (đăng ký trong Tabs với `href: null`, giống pattern `tasks/[id]` đã có). 1 card mới trong `settings.tsx` dẫn sang route đó, chỉ hiện khi CEO + gói Advanced.

**Tech Stack:** Expo SDK 57, expo-router, React Native `StyleSheet`. Không thêm dependency (dùng `Alert` có sẵn trong `react-native`, lần đầu dùng trong app nhưng không cần cài gì thêm).

**Spec thiết kế:** [docs/superpowers/specs/2026-07-14-report-schedules-fe-design.md](../specs/2026-07-14-report-schedules-fe-design.md)

## Global Constraints (frontend/AGENTS.md, frontend/DESIGN.md)

- Expo đã đổi nhiều — tra docs đúng bản tại https://docs.expo.dev/versions/v57.0.0/ trước khi viết code liên quan tới API mới của framework.
- Mọi màn hình dùng token từ `src/ui/theme.ts` (`colors`, `spacing`, `radius`, `type`) — không hardcode hex/số spacing lẻ.
- Đủ 4 trạng thái bắt buộc mỗi khối dữ liệu: loading, empty, error, success.
- FE hiện không có test suite (không Jest/RNTL) — không thêm hạ tầng test mới. Xác minh bằng `npx tsc --noEmit` (baseline hiện tại: 0 lỗi) sau mỗi task.
- **Không xây form tạo lịch trong app** — tạo lịch chỉ qua chat (tool `create_report_schedule` đã có từ Plan 9). Không hiển thị `project_id`/`assignee_id`/`status`/`recipient_id` (UUID thô, không có API resolve tên trong phạm vi plan này).
- Xóa lịch phải có `Alert.alert` xác nhận trước khi gọi API.

---

### Task 1: API layer — `src/api/reportSchedules.ts`

**Files:**
- Create: `frontend/src/api/reportSchedules.ts`

**Interfaces:**
- Produces: `listReportSchedules() => Promise<ReportSchedule[]>`, `deleteReportSchedule(id: string) => Promise<void>`, type `ReportSchedule`. Task 2 dùng cả 3.
- Consumes: `apiFetch<T>(path, opts?)` từ `frontend/src/api/client.ts` (đã có, không sửa).

- [ ] **Step 1: Tạo `frontend/src/api/reportSchedules.ts`**

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

- [ ] **Step 2: Xác minh bằng typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: không có output (0 lỗi).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/reportSchedules.ts
git commit -m "feat(fe): api layer cho lich bao cao dinh ky"
```

---

### Task 2: Màn liệt kê/xóa + entry point trong Cài đặt

**Files:**
- Create: `frontend/app/(main)/report-schedules.tsx`
- Modify: `frontend/app/(main)/settings.tsx`
- Modify: `frontend/app/(main)/_layout.tsx`

**Interfaces:**
- Consumes: `listReportSchedules`, `deleteReportSchedule`, `ReportSchedule` (Task 1).

- [ ] **Step 1: Tạo `frontend/app/(main)/report-schedules.tsx`**

```tsx
import React, { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { ReportSchedule, deleteReportSchedule, listReportSchedules } from "../../src/api/reportSchedules";
import { ErrorText } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";

const WEEKDAY_LABEL = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"];

function scheduleLabel(s: ReportSchedule): string {
  const day = s.weekday === null ? "Hàng ngày" : WEEKDAY_LABEL[s.weekday];
  const time = `${String(s.hour).padStart(2, "0")}:${String(s.minute).padStart(2, "0")}`;
  return `${day}, ${time}`;
}

function ScheduleRow({
  s,
  onDeleted,
  onError,
}: {
  s: ReportSchedule;
  onDeleted: (id: string) => void;
  onError: (msg: string) => void;
}) {
  const confirmDelete = () => {
    Alert.alert("Hủy lịch báo cáo?", "Sẽ không còn tự động gửi báo cáo theo lịch này nữa.", [
      { text: "Hủy", style: "cancel" },
      {
        text: "Xóa",
        style: "destructive",
        onPress: async () => {
          try {
            await deleteReportSchedule(s.id);
            onDeleted(s.id);
          } catch (e: any) {
            onError(String(e?.message ?? e));
          }
        },
      },
    ]);
  };

  return (
    <View style={styles.row}>
      <View style={{ flex: 1 }}>
        <Text style={type.heading}>{scheduleLabel(s)}</Text>
        <Text style={{ color: colors.textSecondary }}>
          Kế tiếp: {new Date(s.next_run_at).toLocaleString("vi-VN")}
        </Text>
        {!s.active && <Text style={{ color: colors.textMuted }}>Tạm dừng</Text>}
      </View>
      <TouchableOpacity onPress={confirmDelete}>
        <Text style={{ color: colors.danger, fontWeight: "700" }}>Xóa</Text>
      </TouchableOpacity>
    </View>
  );
}

export default function ReportSchedules() {
  const [schedules, setSchedules] = useState<ReportSchedule[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listReportSchedules()
      .then(setSchedules)
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, []);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
    >
      {schedules === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {schedules?.length === 0 && (
        <Text style={{ color: colors.textMuted }}>
          Chưa có lịch báo cáo nào — nhắn AI để đặt lịch, ví dụ &quot;gửi báo cáo mỗi sáng thứ 2 lúc
          8h&quot;
        </Text>
      )}
      {schedules && schedules.length > 0 && (
        <View style={styles.card}>
          {schedules.map((s) => (
            <ScheduleRow
              key={s.id}
              s={s}
              onDeleted={(id) => setSchedules((prev) => (prev ? prev.filter((x) => x.id !== id) : prev))}
              onError={setError}
            />
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
});
```

- [ ] **Step 2: Sửa `frontend/app/(main)/settings.tsx`**

File hiện tại (`frontend/app/(main)/settings.tsx`) có dạng:

```tsx
import React, { useEffect, useState } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useAuth } from "../../src/auth/AuthContext";
import { Subscription, getInviteCode, getSubscription } from "../../src/api/dashboard";
import { colors, radius, spacing, type } from "../../src/ui/theme";

export default function Settings() {
  const { user, signOut } = useAuth();
  const [sub, setSub] = useState<Subscription | null>(null);
  const [inviteCode, setInviteCode] = useState<string | null>(null);
  ...
      {sub && (
        <View style={styles.card}>
          <Text style={styles.title}>Gói dịch vụ</Text>
          ...
        </View>
      )}
      {inviteCode && (
```

Sửa đúng 3 chỗ:

1. Thêm `useRouter` vào import `expo-router` (file này hiện chưa import gì từ `expo-router`) — thêm dòng mới ngay sau dòng import `react-native`:

```tsx
import { useRouter } from "expo-router";
```

2. Trong component, ngay sau `const { user, signOut } = useAuth();`, thêm:

```tsx
const router = useRouter();
```

3. Chèn card mới **ngay sau** khối `{sub && (...)}`  và **ngay trước** khối `{inviteCode && (...)}`:

```tsx
      {user?.role === "ceo" && sub?.plan === "advanced" && (
        <TouchableOpacity style={styles.card} onPress={() => router.push("/report-schedules")}>
          <Text style={styles.title}>📅 Báo cáo định kỳ</Text>
          <Text style={{ color: colors.textSecondary }}>Xem và hủy lịch gửi báo cáo tự động</Text>
        </TouchableOpacity>
      )}
```

Không đổi gì khác trong file — 2 khối `{sub && (...)}` và `{inviteCode && (...)}` giữ nguyên y hệt hiện tại, chỉ chèn khối mới ở giữa.

- [ ] **Step 3: Đăng ký route ẩn trong `frontend/app/(main)/_layout.tsx`**

File hiện tại kết thúc bằng:

```tsx
      <Tabs.Screen name="tasks/[id]" options={{ href: null }} />
    </Tabs>
```

Thêm 1 dòng nữa trước `</Tabs>`:

```tsx
      <Tabs.Screen name="tasks/[id]" options={{ href: null }} />
      <Tabs.Screen name="report-schedules" options={{ href: null }} />
    </Tabs>
```

- [ ] **Step 4: Xác minh bằng typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: không có output (0 lỗi).

- [ ] **Step 5: Commit**

```bash
git add frontend/app/\(main\)/report-schedules.tsx frontend/app/\(main\)/settings.tsx frontend/app/\(main\)/_layout.tsx
git commit -m "feat(fe): man liet ke/xoa lich bao cao dinh ky"
```

---

## Ghi chú

- Không có test tự động (FE chưa có hạ tầng test) — `npx tsc --noEmit` là bước xác minh duy nhất. Xác minh bằng mắt qua Expo dev server nên làm thủ công sau khi cả 2 task xong.
- Nếu sau này cần form tạo lịch trong app (không còn qua chat), đó là 1 spec/plan riêng — không mở rộng trong plan này.
