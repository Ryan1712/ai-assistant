# Màn hình Team (khóa/mở/nghỉ việc/đổi vai trò) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CEO vào Settings → "Team" → thấy danh sách toàn công ty, bấm vào 1 người → khóa/mở tài khoản, cho nghỉ việc, hoặc đổi vai trò/quản lý — tất cả 4 hành động BE đã có sẵn từ trước, chỉ chưa có UI.

**Architecture:** 1 sửa BE nhỏ (lộ `manager_id`/`status` qua `UserOut`). FE: 1 API module (`src/api/team.ts`), 2 màn hình (`team.tsx` danh sách, `team/[id].tsx` chi tiết + hành động — route ẩn giống `report-schedules.tsx`/`audit-log.tsx`). Không có endpoint `GET /users/{id}` riêng — màn chi tiết tái dùng `listUsers()` đã tải, tìm theo `id` route param.

**Tech Stack:** FastAPI/Pydantic (BE), Expo SDK 57 + React Native `StyleSheet` (FE). Không thêm dependency mới.

**Spec thiết kế:** [docs/superpowers/specs/2026-07-16-team-screen-design.md](../specs/2026-07-16-team-screen-design.md)

## Global Constraints

- CEO-only toàn bộ (list, detail, cả 4 hành động) — gate CHỈ ở entry point `settings.tsx` (`user?.role === "ceo"`), không có UI hạn chế riêng cho manager/employee, không viết logic quyền mới ở FE — mọi validate dựa vào BE trả lỗi.
- `UserOut` thêm đúng 2 field: `manager_id: uuid.UUID | None`, `status: str` — không đổi field nào khác, không đổi endpoint nào.
- Ô "Người kế nhiệm" luôn có sẵn, tùy chọn — không gọi API kiểm tra trước, dựa vào lỗi `422 successor_required` từ BE.
- Không map lỗi BE sang message tiếng Việt riêng — hiện nguyên message BE trả về qua `ErrorText`/`Alert`.
- Route ẩn (`href: null`), không phải tab mới hiện trong tab bar.
- FE không có test suite — `npx tsc --noEmit` (0 lỗi) là xác minh duy nhất. BE dùng TDD (pytest) như thường lệ.
- Đổi API contract (BE) → chạy lại `python scripts/export_openapi.py` từ `backend/`.

---

### Task 1: BE — thêm `manager_id`/`status` vào `UserOut`

**Files:**
- Modify: `backend/app/schemas.py:27-34`
- Test: `backend/tests/test_users_api.py`

**Interfaces:**
- Produces: `UserOut` có thêm `manager_id: uuid.UUID | None`, `status: str`. Task 2 (FE) dùng 2 field này trong `TeamUser` type.

- [ ] **Step 1: Viết test thất bại trong `backend/tests/test_users_api.py`**

```python
import pytest

from tests.conftest import _ceo_headers, _invite_and_join


@pytest.mark.asyncio
async def test_user_out_includes_manager_id_and_status(client):
    ceo_h = await _ceo_headers(client)
    m1 = await _invite_and_join(client, ceo_h, "manager", "m1@a.vn")
    e1 = await _invite_and_join(client, ceo_h, "employee", "e1@a.vn", m1["user"]["id"])

    listed = (await client.get("/api/v1/users", headers=ceo_h)).json()
    e1_out = next(u for u in listed if u["email"] == "e1@a.vn")
    assert e1_out["manager_id"] == m1["user"]["id"]
    assert e1_out["status"] == "active"

    ceo_out = next(u for u in listed if u["email"] == "ceo@a.vn")
    assert ceo_out["manager_id"] is None
    assert ceo_out["status"] == "active"

    me = (await client.get("/api/v1/users/me", headers=ceo_h)).json()
    assert "manager_id" in me
    assert "status" in me
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: `cd backend && pytest tests/test_users_api.py -v`
Expected: FAIL — `KeyError: 'manager_id'` (field chưa tồn tại trong response `UserOut` hiện tại).

- [ ] **Step 3: Sửa `UserOut` trong `backend/app/schemas.py`**

Thay khối `class UserOut` (dòng 27-34 hiện tại) bằng:

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

- [ ] **Step 4: Chạy test, xác nhận PASS**

Run: `cd backend && pytest tests/test_users_api.py -v`
Expected: PASS.

- [ ] **Step 5: Chạy toàn bộ test suite**

Run: `cd backend && pytest tests/ -v`
Expected: PASS toàn bộ — đặc biệt `tests/test_permissions.py`, `tests/test_lock.py`, `tests/test_auth.py` (đều gọi `/api/v1/users`/`/me`) không bị đỏ vì thêm field mới (Pydantic thêm field không phá test cũ chỉ check field cụ thể, không check dict bằng nhau tuyệt đối).

- [ ] **Step 6: Xuất lại OpenAPI contract cho FE**

Run: `cd backend && python scripts/export_openapi.py`
Expected: `openapi.json` ở repo root cập nhật, `UserOut` schema có thêm `manager_id`/`status`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas.py backend/tests/test_users_api.py openapi.json
git commit -m "feat(be): UserOut them manager_id + status cho man hinh Team"
```

---

### Task 2: FE — API module `frontend/src/api/team.ts`

**Files:**
- Create: `frontend/src/api/team.ts`

**Interfaces:**
- Produces: `type TeamUser`, `type OffboardResult`, `type ChangeRoleResult`, `listUsers()`, `lockUser(id)`, `unlockUser(id)`, `offboardUser(id, successorId?)`, `changeRole(id, body)`. Task 3/4/5 dùng các hàm/type này.
- Consumes: `apiFetch<T>` từ `frontend/src/api/client.ts` (đã có, không sửa).

- [ ] **Step 1: Tạo `frontend/src/api/team.ts`**

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

- [ ] **Step 2: Xác minh bằng typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: không có output (0 lỗi).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/team.ts
git commit -m "feat(fe): api layer team (list/lock/unlock/offboard/change-role)"
```

---

### Task 3: FE — Màn danh sách `team.tsx` + đăng ký route + entry point

**Files:**
- Create: `frontend/app/(main)/team.tsx`
- Modify: `frontend/app/(main)/_layout.tsx`
- Modify: `frontend/app/(main)/settings.tsx`

**Interfaces:**
- Consumes: `TeamUser`, `listUsers` (Task 2).

- [ ] **Step 1: Tạo `frontend/app/(main)/team.tsx`**

```tsx
import React, { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useRouter } from "expo-router";
import { TeamUser, listUsers } from "../../src/api/team";
import { ErrorText } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";

function roleLabel(role: TeamUser["role"]): string {
  return role === "ceo" ? "CEO" : role === "manager" ? "Manager" : "Nhân viên";
}

function TeamRow({ u }: { u: TeamUser }) {
  const router = useRouter();
  return (
    <TouchableOpacity style={styles.row} onPress={() => router.push(`/team/${u.id}`)}>
      <View style={{ flex: 1 }}>
        <Text style={type.body}>{u.full_name}</Text>
        <Text style={{ color: colors.textSecondary }}>{roleLabel(u.role)}</Text>
      </View>
      {u.status === "locked" && (
        <Text style={{ color: colors.danger, fontWeight: "700" }}>Đã khóa</Text>
      )}
    </TouchableOpacity>
  );
}

export default function Team() {
  const [users, setUsers] = useState<TeamUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listUsers()
      .then(setUsers)
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, []);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
    >
      {users === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {users?.length === 0 && (
        <Text style={{ color: colors.textMuted }}>Chưa có ai trong công ty</Text>
      )}
      {users && users.length > 0 && (
        <View style={styles.card}>
          {users.map((u) => (
            <TeamRow key={u.id} u={u} />
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

- [ ] **Step 2: Đăng ký route ẩn cho `team` trong `frontend/app/(main)/_layout.tsx`**

Sửa file — thêm 1 dòng ngay sau `audit-log` (dòng 40 hiện tại). CHỈ đăng ký `team` (file tạo ở task này) — KHÔNG đăng ký `team/[id]` ở đây (file đó Task 4 mới tạo; đăng ký 1 route chưa có file backing dễ gây lỗi runtime của expo-router — Task 4 sẽ tự thêm dòng đăng ký của nó cùng lúc tạo file, đúng tiền lệ plan `search-fe` đã làm với `tasks/[id]`):

```tsx
      <Tabs.Screen name="tasks/[id]" options={{ href: null }} />
      <Tabs.Screen name="report-schedules" options={{ href: null }} />
      <Tabs.Screen name="audit-log" options={{ href: null }} />
      <Tabs.Screen name="team" options={{ href: null }} />
```

(3 dòng đầu giữ nguyên, chỉ để bạn thấy đúng vị trí chèn dòng cuối.)

- [ ] **Step 3: Thêm entry point trong `frontend/app/(main)/settings.tsx`**

Sửa file — thêm 1 card mới ngay sau khối `audit-log` (dòng 51-56 hiện tại):

```tsx
      {user?.role === "ceo" && (
        <TouchableOpacity style={styles.card} onPress={() => router.push("/audit-log")}>
          <Text style={styles.title}>📜 Nhật ký thay đổi</Text>
          <Text style={{ color: colors.textSecondary }}>Xem lịch sử hoạt động của công ty</Text>
        </TouchableOpacity>
      )}
      {user?.role === "ceo" && (
        <TouchableOpacity style={styles.card} onPress={() => router.push("/team")}>
          <Text style={styles.title}>👥 Team</Text>
          <Text style={{ color: colors.textSecondary }}>Quản lý nhân sự: khóa/mở, nghỉ việc, đổi vai trò</Text>
        </TouchableOpacity>
      )}
```

(Khối `audit-log` giữ nguyên không đổi — chỉ thêm khối `team` mới ngay sau.)

- [ ] **Step 4: Xác minh bằng typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: TypeScript sẽ CHƯA báo lỗi cho `router.push("/team")`/`router.push(\`/team/${u.id}\`)` trừ khi dự án bật `experimental.typedRoutes` trong `app.json` (kiểm tra file này trước) — nếu có bật và báo lỗi vì route `team/[id]` chưa có file thật (chỉ mới khai báo trong `_layout.tsx`), dùng tạm `as any` ở lời gọi `router.push` liên quan, ghi rõ lý do, Task 4 tạo file xong sẽ bỏ `as any` đó (xem Step 4 của Task 4).
Nếu không bật typed routes: expect 0 lỗi bình thường.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/\(main\)/team.tsx frontend/app/\(main\)/_layout.tsx frontend/app/\(main\)/settings.tsx
git commit -m "feat(fe): man danh sach Team + dang ky route + entry point Settings"
```

---

### Task 4: FE — Màn chi tiết `team/[id].tsx` (thông tin + khóa/mở)

**Files:**
- Create: `frontend/app/(main)/team/[id].tsx`
- Modify: `frontend/app/(main)/_layout.tsx`

**Interfaces:**
- Consumes: `TeamUser`, `listUsers`, `lockUser`, `unlockUser` (Task 2).
- Produces: cấu trúc file `team/[id].tsx` với state `users`/`error`/`lockBusy`, hàm `load()`, biến `target`/`manager` — Task 5 sẽ thêm state/hàm/UI mới vào ĐÚNG file này (không tạo file khác), giữ nguyên các state/hàm này.

- [ ] **Step 1: Tra docs Expo Router v57 cho route lồng `team/[id]`**

Trước khi viết code, xác nhận `useLocalSearchParams<{ id: string }>()` hoạt động giống hệt cách `tasks/[id].tsx` đang dùng (đã có tiền lệ trong dự án, không cần tra thêm nếu tin tưởng tiền lệ này vẫn đúng — chỉ tra lại nếu code dưới đây không chạy như mong đợi).

- [ ] **Step 2: Tạo `frontend/app/(main)/team/[id].tsx`**

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
import { useLocalSearchParams } from "expo-router";
import { TeamUser, listUsers, lockUser, unlockUser } from "../../../src/api/team";
import { ErrorText } from "../../../src/ui/form";
import { colors, radius, spacing, type } from "../../../src/ui/theme";

function roleLabel(role: TeamUser["role"]): string {
  return role === "ceo" ? "CEO" : role === "manager" ? "Manager" : "Nhân viên";
}

export default function TeamDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [users, setUsers] = useState<TeamUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lockBusy, setLockBusy] = useState(false);

  const load = () => {
    listUsers()
      .then(setUsers)
      .catch((e: any) => setError(String(e?.message ?? e)));
  };

  useEffect(() => {
    load();
  }, []);

  const target = users?.find((u) => u.id === id) ?? null;
  const manager = target?.manager_id ? users?.find((u) => u.id === target.manager_id) : null;

  const toggleLock = () => {
    if (!target) return;
    const locking = target.status === "active";
    Alert.alert(
      locking ? "Khóa tài khoản?" : "Mở khóa tài khoản?",
      locking
        ? `${target.full_name} sẽ bị đăng xuất khỏi mọi thiết bị.`
        : `${target.full_name} sẽ đăng nhập lại được.`,
      [
        { text: "Hủy", style: "cancel" },
        {
          text: locking ? "Khóa" : "Mở khóa",
          style: locking ? "destructive" : "default",
          onPress: async () => {
            setLockBusy(true);
            try {
              await (locking ? lockUser(target.id) : unlockUser(target.id));
              load();
            } catch (e: any) {
              Alert.alert("Không thực hiện được", String(e?.message ?? e));
            } finally {
              setLockBusy(false);
            }
          },
        },
      ],
    );
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
    >
      {users === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {users !== null && !target && <ErrorText error="Không tìm thấy người này" />}
      {target && (
        <>
          <View style={styles.card}>
            <Text style={styles.title}>{target.full_name}</Text>
            <Text style={{ color: colors.textSecondary }}>{target.email}</Text>
            <Text style={{ marginTop: spacing.xs, color: colors.text }}>
              Vai trò: {roleLabel(target.role)}
            </Text>
            {manager && (
              <Text style={{ color: colors.text }}>Báo cáo cho: {manager.full_name}</Text>
            )}
            <Text style={{ color: target.status === "locked" ? colors.danger : colors.success }}>
              {target.status === "locked" ? "Đã khóa" : "Đang hoạt động"}
            </Text>
          </View>
          <View style={styles.card}>
            <Text style={styles.title}>Hành động</Text>
            <TouchableOpacity onPress={toggleLock} disabled={lockBusy}>
              {lockBusy ? (
                <ActivityIndicator color={colors.primary} />
              ) : (
                <Text style={{ color: colors.primary, fontWeight: "700" }}>
                  {target.status === "locked" ? "Mở khóa" : "Khóa tài khoản"}
                </Text>
              )}
            </TouchableOpacity>
          </View>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  title: { ...type.heading },
});
```

- [ ] **Step 3: Đăng ký route ẩn cho `team/[id]` trong `frontend/app/(main)/_layout.tsx`**

Thêm 1 dòng ngay sau dòng `team` (thêm ở Task 3 Step 2):

```tsx
      <Tabs.Screen name="team" options={{ href: null }} />
      <Tabs.Screen name="team/[id]" options={{ href: null }} />
```

- [ ] **Step 4: Nếu Task 3 phải dùng `as any` tạm cho `router.push`, bỏ đi ngay bây giờ**

Route `team/[id]` giờ đã tồn tại thật và đã đăng ký — nếu Task 3 Step 4 phải thêm `as any` vì typed-routes, xóa `as any` đó trong `team.tsx` (dòng `router.push(\`/team/${u.id}\`)`).

- [ ] **Step 5: Xác minh bằng typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: không có output (0 lỗi).

- [ ] **Step 6: Commit**

```bash
git add frontend/app/\(main\)/team/\[id\].tsx frontend/app/\(main\)/team.tsx frontend/app/\(main\)/_layout.tsx
git commit -m "feat(fe): man chi tiet Team - thong tin + khoa/mo tai khoan"
```

---

### Task 5: FE — Panel "Cho nghỉ việc" + "Đổi vai trò" trong `team/[id].tsx`

**Files:**
- Modify: `frontend/app/(main)/team/[id].tsx` (thay TOÀN BỘ nội dung file — Task 4 đã tạo file, task này viết lại đầy đủ hơn, giữ nguyên mọi thứ Task 4 đã có, chỉ thêm mới)

**Interfaces:**
- Consumes: `TeamUser`, `ChangeRoleResult`, `listUsers`, `lockUser`, `unlockUser`, `offboardUser`, `changeRole` (Task 2).
- Produces: component `PersonPicker({label, people, value, onChange})` cục bộ trong file — dùng chung cho cả 2 panel (kế nhiệm + quản lý).

- [ ] **Step 1: Thay toàn bộ nội dung `frontend/app/(main)/team/[id].tsx`**

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
import { useLocalSearchParams } from "expo-router";
import {
  ChangeRoleResult,
  TeamUser,
  changeRole,
  listUsers,
  lockUser,
  offboardUser,
  unlockUser,
} from "../../../src/api/team";
import { ErrorText } from "../../../src/ui/form";
import { colors, radius, spacing, type } from "../../../src/ui/theme";

function roleLabel(role: TeamUser["role"]): string {
  return role === "ceo" ? "CEO" : role === "manager" ? "Manager" : "Nhân viên";
}

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
    <View style={{ marginTop: spacing.sm }}>
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

export default function TeamDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [users, setUsers] = useState<TeamUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lockBusy, setLockBusy] = useState(false);

  const [showOffboard, setShowOffboard] = useState(false);
  const [offboardSuccessor, setOffboardSuccessor] = useState<string | null>(null);
  const [offboardBusy, setOffboardBusy] = useState(false);
  const [offboardError, setOffboardError] = useState<string | null>(null);

  const [showRoleForm, setShowRoleForm] = useState(false);
  const [newRole, setNewRole] = useState<TeamUser["role"] | null>(null);
  const [newManager, setNewManager] = useState<string | null>(null);
  const [roleSuccessor, setRoleSuccessor] = useState<string | null>(null);
  const [roleBusy, setRoleBusy] = useState(false);
  const [roleError, setRoleError] = useState<string | null>(null);

  const load = () => {
    listUsers()
      .then(setUsers)
      .catch((e: any) => setError(String(e?.message ?? e)));
  };

  useEffect(() => {
    load();
  }, []);

  const target = users?.find((u) => u.id === id) ?? null;
  const manager = target?.manager_id ? users?.find((u) => u.id === target.manager_id) : null;
  const successorCandidates =
    users?.filter((u) => u.id !== target?.id && u.status !== "locked") ?? [];
  const managerCandidates = users?.filter((u) => u.role === "manager") ?? [];

  const toggleLock = () => {
    if (!target) return;
    const locking = target.status === "active";
    Alert.alert(
      locking ? "Khóa tài khoản?" : "Mở khóa tài khoản?",
      locking
        ? `${target.full_name} sẽ bị đăng xuất khỏi mọi thiết bị.`
        : `${target.full_name} sẽ đăng nhập lại được.`,
      [
        { text: "Hủy", style: "cancel" },
        {
          text: locking ? "Khóa" : "Mở khóa",
          style: locking ? "destructive" : "default",
          onPress: async () => {
            setLockBusy(true);
            try {
              await (locking ? lockUser(target.id) : unlockUser(target.id));
              load();
            } catch (e: any) {
              Alert.alert("Không thực hiện được", String(e?.message ?? e));
            } finally {
              setLockBusy(false);
            }
          },
        },
      ],
    );
  };

  const submitOffboard = () => {
    if (!target) return;
    Alert.alert("Cho nghỉ việc?", `${target.full_name} sẽ bị khóa tài khoản ngay.`, [
      { text: "Hủy", style: "cancel" },
      {
        text: "Xác nhận",
        style: "destructive",
        onPress: async () => {
          setOffboardBusy(true);
          setOffboardError(null);
          try {
            await offboardUser(target.id, offboardSuccessor ?? undefined);
            setShowOffboard(false);
            load();
          } catch (e: any) {
            setOffboardError(String(e?.message ?? e));
          } finally {
            setOffboardBusy(false);
          }
        },
      },
    ]);
  };

  const submitRoleChange = async () => {
    if (!target) return;
    setRoleBusy(true);
    setRoleError(null);
    try {
      const result: ChangeRoleResult = await changeRole(target.id, {
        new_role: newRole ?? undefined,
        new_manager_id: newRole === "employee" ? newManager ?? undefined : undefined,
        successor_id: roleSuccessor ?? undefined,
      });
      void result;
      setShowRoleForm(false);
      load();
    } catch (e: any) {
      setRoleError(String(e?.message ?? e));
    } finally {
      setRoleBusy(false);
    }
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
    >
      {users === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {users !== null && !target && <ErrorText error="Không tìm thấy người này" />}
      {target && (
        <>
          <View style={styles.card}>
            <Text style={styles.title}>{target.full_name}</Text>
            <Text style={{ color: colors.textSecondary }}>{target.email}</Text>
            <Text style={{ marginTop: spacing.xs, color: colors.text }}>
              Vai trò: {roleLabel(target.role)}
            </Text>
            {manager && (
              <Text style={{ color: colors.text }}>Báo cáo cho: {manager.full_name}</Text>
            )}
            <Text style={{ color: target.status === "locked" ? colors.danger : colors.success }}>
              {target.status === "locked" ? "Đã khóa" : "Đang hoạt động"}
            </Text>
          </View>

          <View style={styles.card}>
            <Text style={styles.title}>Hành động</Text>

            <TouchableOpacity onPress={toggleLock} disabled={lockBusy}>
              {lockBusy ? (
                <ActivityIndicator color={colors.primary} />
              ) : (
                <Text style={{ color: colors.primary, fontWeight: "700" }}>
                  {target.status === "locked" ? "Mở khóa" : "Khóa tài khoản"}
                </Text>
              )}
            </TouchableOpacity>

            <TouchableOpacity
              onPress={() => setShowOffboard((s) => !s)}
              style={{ marginTop: spacing.md }}
            >
              <Text style={{ color: colors.danger, fontWeight: "700" }}>Cho nghỉ việc</Text>
            </TouchableOpacity>
            {showOffboard && (
              <View style={{ marginTop: spacing.sm }}>
                <PersonPicker
                  label="Người kế nhiệm (nếu cần)"
                  people={successorCandidates}
                  value={offboardSuccessor}
                  onChange={setOffboardSuccessor}
                />
                <ErrorText error={offboardError} />
                <TouchableOpacity
                  onPress={submitOffboard}
                  disabled={offboardBusy}
                  style={{ marginTop: spacing.sm }}
                >
                  {offboardBusy ? (
                    <ActivityIndicator color={colors.danger} />
                  ) : (
                    <Text style={{ color: colors.danger, fontWeight: "700" }}>
                      Xác nhận nghỉ việc
                    </Text>
                  )}
                </TouchableOpacity>
              </View>
            )}

            <TouchableOpacity
              onPress={() => {
                setShowRoleForm((s) => !s);
                setNewRole(target.role);
              }}
              style={{ marginTop: spacing.md }}
            >
              <Text style={{ color: colors.primary, fontWeight: "700" }}>Đổi vai trò</Text>
            </TouchableOpacity>
            {showRoleForm && (
              <View style={{ marginTop: spacing.sm }}>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  {(["ceo", "manager", "employee"] as const).map((r) => (
                    <TouchableOpacity
                      key={r}
                      onPress={() => setNewRole(r)}
                      style={[styles.chip, newRole === r && styles.chipActive]}
                    >
                      <Text style={{ color: newRole === r ? colors.onPrimary : colors.text }}>
                        {roleLabel(r)}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
                {newRole === "employee" && (
                  <PersonPicker
                    label="Quản lý"
                    people={managerCandidates}
                    value={newManager}
                    onChange={setNewManager}
                  />
                )}
                <PersonPicker
                  label="Người kế nhiệm (nếu cần)"
                  people={successorCandidates}
                  value={roleSuccessor}
                  onChange={setRoleSuccessor}
                />
                <ErrorText error={roleError} />
                <TouchableOpacity
                  onPress={submitRoleChange}
                  disabled={roleBusy}
                  style={{ marginTop: spacing.sm }}
                >
                  {roleBusy ? (
                    <ActivityIndicator color={colors.primary} />
                  ) : (
                    <Text style={{ color: colors.primary, fontWeight: "700" }}>Xác nhận</Text>
                  )}
                </TouchableOpacity>
              </View>
            )}
          </View>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  title: { ...type.heading },
  chip: {
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: radius.md,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
  },
  chipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  pickerList: {
    marginTop: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
  },
  pickerRow: {
    padding: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
});
```

Ghi chú: `submitRoleChange` cố ý gán `result` rồi `void result` — `changeRole()` trả về `ChangeRoleResult` với dữ liệu tóm tắt (số report/project bàn giao) nhưng plan này không hiển thị gì thêm từ đó (`load()` gọi lại `listUsers()` là đủ để màn hình phản ánh đúng trạng thái mới) — giữ biến có kiểu tường minh cho rõ ràng, không phải để dùng sau.

- [ ] **Step 2: Xác minh bằng typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: không có output (0 lỗi).

- [ ] **Step 3: Commit**

```bash
git add frontend/app/\(main\)/team/\[id\].tsx
git commit -m "feat(fe): panel nghi viec + doi vai tro trong man chi tiet Team"
```

---

## Ghi chú

- Không có test tự động cho các task FE (FE chưa có hạ tầng test) — `npx tsc --noEmit` là bước xác minh duy nhất bắt buộc agent chạy. Xác minh bằng mắt qua Expo dev server nên làm thủ công sau khi cả 5 task xong (checklist đầy đủ ở spec FE §8 "Testing / Verification").
- Không có chế độ xem cho manager/employee — cố ý theo spec §1, không thêm trong plan này.
