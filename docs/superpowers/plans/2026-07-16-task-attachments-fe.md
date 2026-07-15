# FE đính kèm tài liệu trong task — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans hoặc superpowers:subagent-driven-development để thực thi plan này task-by-task. Checkbox (`- [ ]`) để tracking.

**Goal:** Trong màn hình chi tiết task (`app/(main)/tasks/[id].tsx`), user thấy danh sách tài liệu đính kèm của task, đính kèm file mới, và tải file về để mở/chia sẻ.

**Architecture:** 1 file API mới (`src/api/attachments.ts`) gọi thẳng 3 endpoint BE đã có (`/api/v1/tasks/{id}/attachments` GET/POST, `/api/v1/attachments/{id}/file` GET). 1 section mới trong `[id].tsx` với 2 subcomponent cục bộ (`AttachmentsSection`, `AttachmentRow`), theo đúng pattern `useState` + `apiFetch` + card/row layout đã dùng ở `report-schedules.tsx`/`today.tsx`. Chọn file bằng `expo-document-picker`, tải + chia sẻ bằng `expo-file-system` (API class `File`/`Paths` mới của SDK 57, không phải API hàm cũ) + `expo-sharing`.

**Tech Stack:** Expo SDK 57 (`~57.0.4`), expo-router, React Native `StyleSheet`. Thêm 3 dependency mới: `expo-document-picker`, `expo-file-system`, `expo-sharing`.

**Spec thiết kế:** [docs/superpowers/specs/2026-07-16-task-attachments-fe-design.md](../specs/2026-07-16-task-attachments-fe-design.md)
**Spec BE liên quan:** [docs/superpowers/specs/2026-07-15-task-attachments-design.md](../specs/2026-07-15-task-attachments-design.md)

## Global Constraints (frontend/AGENTS.md, frontend/DESIGN.md, spec FE)

- Expo đã đổi nhiều bản gần đây — dự án đang ở SDK `~57.0.4`. `expo-file-system` ở SDK 57 dùng API class mới (`File`, `Directory`, `Paths`) — API hàm cũ (`FileSystem.writeAsStringAsync`, `FileSystem.cacheDirectory`) đã **deprecated và sẽ throw runtime**, plan này đã tra đúng docs bản 57 và dùng API mới xuyên suốt — không tự ý đổi lại API cũ.
- Mọi màn hình dùng token từ `src/ui/theme.ts` (`colors`, `spacing`, `radius`, `type`) — không hardcode hex/số spacing lẻ.
- Đủ 4 trạng thái bắt buộc mỗi khối dữ liệu: loading, empty, error, success — không để màn trắng/lỗi câm.
- Whitelist MIME cho file picker phải khớp whitelist đuôi file bên BE: `.pdf .doc .docx .xls .xlsx .ppt .pptx .txt .png .jpg .jpeg .zip` (`backend/app/services/attachment_service.py` `_ALLOWED_EXTS`).
- Giới hạn dung lượng: 20MB (`backend/app/services/attachment_service.py` `_MAX_FILE_SIZE`) — check client-side trước khi upload để fail fast.
- Không có UI xóa attachment, không preview file nội bộ (dùng share sheet để mở app khác) — theo quyết định brainstorming trong spec FE §1.
- FE hiện không có test suite (không Jest/RNTL) — không thêm hạ tầng test mới trong plan này. Xác minh bằng `npx tsc --noEmit` sau mỗi task, thay cho unit test.

---

### Task 1: API layer — `frontend/src/api/attachments.ts`

**Files:**
- Create: `frontend/src/api/attachments.ts`

**Interfaces:**
- Produces: `type Attachment`, `ATTACHMENT_MIME_TYPES: string[]`, `ATTACHMENT_MAX_SIZE: number`, `listTaskAttachments(taskId: string) => Promise<Attachment[]>`, `uploadTaskAttachment(taskId: string, file: {uri: string; name: string; mimeType: string}) => Promise<Attachment>`, `fetchAttachmentBytes(attachmentId: string) => Promise<ArrayBuffer>`. Task 2 dùng `Attachment`/`ATTACHMENT_MIME_TYPES`/`ATTACHMENT_MAX_SIZE`/`listTaskAttachments`/`uploadTaskAttachment`. Task 3 dùng `fetchAttachmentBytes`.
- Consumes: `apiFetch<T>`, `API_URL` từ `frontend/src/api/client.ts` (đã có, không sửa); `getTokens` từ `frontend/src/auth/tokenStore.ts` (đã có, không sửa).

Không cần package mới cho task này — chỉ dùng `fetch`/`FormData` chuẩn, giống `voice.ts`.

- [ ] **Step 1: Tạo `frontend/src/api/attachments.ts`**

```ts
import { API_URL, apiFetch } from "./client";
import { getTokens } from "../auth/tokenStore";

export type Attachment = {
  id: string;
  task_id: string;
  author_id: string;
  original_filename: string;
  file_size: number;
  created_at: string;
};

// Khớp backend/app/services/attachment_service.py _ALLOWED_EXTS
export const ATTACHMENT_MIME_TYPES = [
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document", // .docx
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", // .xlsx
  "application/vnd.ms-powerpoint",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation", // .pptx
  "text/plain",
  "image/png",
  "image/jpeg",
  "application/zip",
];

// Khớp backend/app/services/attachment_service.py _MAX_FILE_SIZE
export const ATTACHMENT_MAX_SIZE = 20 * 1024 * 1024;

export const listTaskAttachments = (taskId: string) =>
  apiFetch<Attachment[]>(`/api/v1/tasks/${taskId}/attachments`);

export const uploadTaskAttachment = (
  taskId: string,
  file: { uri: string; name: string; mimeType: string },
) => {
  const form = new FormData();
  // RN FormData nhận {uri, name, type} cho file — cast vì DOM types không biết
  form.append("file", { uri: file.uri, name: file.name, type: file.mimeType } as unknown as Blob);
  return apiFetch<Attachment>(`/api/v1/tasks/${taskId}/attachments`, {
    method: "POST",
    body: form,
  });
};

// apiFetch luôn parse JSON — endpoint này trả binary nên gọi fetch trực tiếp,
// tự gắn Bearer token giống cách client.ts đang làm.
export async function fetchAttachmentBytes(attachmentId: string): Promise<ArrayBuffer> {
  const tokens = await getTokens();
  const resp = await fetch(`${API_URL}/api/v1/attachments/${attachmentId}/file`, {
    headers: tokens?.access_token ? { Authorization: `Bearer ${tokens.access_token}` } : {},
  });
  if (!resp.ok) throw new Error(`download_failed_${resp.status}`);
  return resp.arrayBuffer();
}
```

- [ ] **Step 2: Xác minh bằng typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: không có output (0 lỗi) — file mới chỉ export type/function thuần, không có logic để lỗi.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/attachments.ts
git commit -m "feat(fe): api layer dinh kem tai lieu (list/upload/download bytes)"
```

---

### Task 2: Danh sách + đính kèm file — sửa `frontend/app/(main)/tasks/[id].tsx`

**Files:**
- Modify: `frontend/app/(main)/tasks/[id].tsx`
- Modify: `frontend/package.json` (qua `npx expo install`, không tự sửa tay)

**Interfaces:**
- Consumes: `Attachment`, `ATTACHMENT_MIME_TYPES`, `ATTACHMENT_MAX_SIZE`, `listTaskAttachments`, `uploadTaskAttachment` (Task 1).
- Produces: component `AttachmentsSection({ taskId: string })` và `AttachmentRow({ a: Attachment })` trong `[id].tsx` — Task 3 sẽ sửa `AttachmentRow` để thêm `downloading`/`onDownload` props (chữ ký sẽ đổi ở Task 3, xem ghi chú cuối task).

- [ ] **Step 1: Cài package `expo-document-picker`**

Run: `cd frontend && npx expo install expo-document-picker`
Expected: `expo-document-picker` xuất hiện trong `dependencies` của `frontend/package.json` với version khớp SDK 57 (do `expo install` tự chọn).

- [ ] **Step 2: Tra docs Expo SDK 57 cho `expo-document-picker`**

Trước khi viết code, xem https://docs.expo.dev/versions/v57.0.0/sdk/document-picker/ để xác nhận chữ ký `DocumentPicker.getDocumentAsync(options)` hiện hành — plan này đã tra sẵn và ghi lại dưới đây, chỉ cần đối chiếu nếu code không chạy đúng như mô tả:
  - `getDocumentAsync({ type: string | string[] })` — `type` là mảng MIME type để lọc.
  - Kết quả thành công: `{ canceled: false, assets: [{ uri, name, mimeType?, size?, lastModified }] }`.
  - Kết quả hủy: `{ canceled: true, assets: null }`.

- [ ] **Step 3: Sửa `frontend/app/(main)/tasks/[id].tsx`**

Thay toàn bộ nội dung file bằng:

```tsx
import React, { useEffect, useState } from "react";
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import * as DocumentPicker from "expo-document-picker";
import { TaskDetail, getTask } from "../../../src/api/tasks";
import {
  ATTACHMENT_MAX_SIZE,
  ATTACHMENT_MIME_TYPES,
  Attachment,
  listTaskAttachments,
  uploadTaskAttachment,
} from "../../../src/api/attachments";
import { ErrorText } from "../../../src/ui/form";
import { colors, radius, spacing, type } from "../../../src/ui/theme";

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function AttachmentRow({ a }: { a: Attachment }) {
  return (
    <View style={styles.row}>
      <View style={{ flex: 1 }}>
        <Text numberOfLines={1}>{a.original_filename}</Text>
        <Text style={{ color: colors.textSecondary }}>
          {formatFileSize(a.file_size)} — {new Date(a.created_at).toLocaleDateString("vi-VN")}
        </Text>
      </View>
    </View>
  );
}

function AttachmentsSection({ taskId }: { taskId: string }) {
  const [attachments, setAttachments] = useState<Attachment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    listTaskAttachments(taskId)
      .then(setAttachments)
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, [taskId]);

  const handlePick = async () => {
    const result = await DocumentPicker.getDocumentAsync({ type: ATTACHMENT_MIME_TYPES });
    if (result.canceled) return;
    const asset = result.assets[0];
    if (asset.size !== undefined && asset.size > ATTACHMENT_MAX_SIZE) {
      setError("File vượt quá 20MB.");
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const uploaded = await uploadTaskAttachment(taskId, {
        uri: asset.uri,
        name: asset.name,
        mimeType: asset.mimeType ?? "application/octet-stream",
      });
      setAttachments((prev) => (prev ? [uploaded, ...prev] : [uploaded]));
    } catch (e: any) {
      // ApiError.detail là chuỗi raw từ BE (vd "unsupported_file_format") — map sang
      // message tiếng Việt cho 2 lỗi 422 spec yêu cầu, còn lại dùng message chung.
      if (e?.status === 422 && e?.detail === "unsupported_file_format") {
        setError("Định dạng file không được hỗ trợ.");
      } else if (e?.status === 422 && e?.detail === "file_too_large") {
        setError("File vượt quá 20MB.");
      } else {
        setError(String(e?.message ?? e));
      }
    } finally {
      setUploading(false);
    }
  };

  return (
    <View style={styles.card}>
      <View style={styles.sectionHeader}>
        <Text style={styles.cardTitle}>Tài liệu đính kèm</Text>
        <TouchableOpacity
          onPress={handlePick}
          disabled={uploading}
          accessibilityLabel="Đính kèm tài liệu"
        >
          {uploading ? (
            <ActivityIndicator color={colors.primary} />
          ) : (
            <Text style={{ color: colors.primary, fontWeight: "700" }}>+ Đính kèm</Text>
          )}
        </TouchableOpacity>
      </View>
      {attachments === null && !error && <ActivityIndicator color={colors.primary} />}
      <ErrorText error={error} />
      {attachments?.length === 0 && (
        <Text style={{ color: colors.textMuted }}>
          Chưa có tài liệu nào — bấm + Đính kèm để thêm
        </Text>
      )}
      {attachments?.map((a) => (
        <AttachmentRow key={a.id} a={a} />
      ))}
    </View>
  );
}

export default function TaskDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const t = await getTask(id);
        if (!cancelled) setTask(t);
      } catch (e: any) {
        if (!cancelled) setError(String(e?.message ?? e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
    >
      {!task && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {task && (
        <>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>{task.title}</Text>
            <Text style={styles.meta}>
              {task.status} — {task.percent}%
            </Text>
            {task.description !== "" && <Text style={styles.body}>{task.description}</Text>}
            {task.deadline && (
              <Text style={styles.meta}>
                Deadline: {new Date(task.deadline).toLocaleDateString("vi-VN")}
              </Text>
            )}
            <Text style={styles.meta}>Ưu tiên: {task.priority}</Text>
          </View>
          <AttachmentsSection taskId={id} />
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
  cardTitle: { ...type.heading },
  meta: { color: colors.textSecondary },
  body: { ...type.body },
  sectionHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
});
```

Nếu Step 2 phát hiện `useLocalSearchParams<{ id: string }>()` trả `id` kiểu khác hiện hành (vd `string | string[]`) so với những gì file hiện tại giả định, sửa dòng khai báo và mọi chỗ dùng `id` cho khớp — không đổi phần còn lại của file. (File hiện tại đã dùng `getTask(id)` trực tiếp không ép kiểu, nên nhiều khả năng không cần sửa gì.)

- [ ] **Step 4: Xác minh bằng typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: không có output (0 lỗi).

- [ ] **Step 5: Commit**

```bash
git add frontend/app/\(main\)/tasks/\[id\].tsx frontend/package.json frontend/package-lock.json
git commit -m "feat(fe): danh sach + dinh kem tai lieu trong man chi tiet task"
```

**Ghi chú cho Task 3:** `AttachmentRow` ở task này chỉ hiển thị (không bấm được). Task 3 sẽ sửa `AttachmentRow` thêm props `downloading: boolean` và `onDownload: (a: Attachment) => void`, bọc nội dung trong `TouchableOpacity`, và `AttachmentsSection` thêm state `downloadingId` + hàm `handleDownload`. Interface hiện tại của `AttachmentRow({ a: Attachment })` sẽ đổi thành `AttachmentRow({ a, downloading, onDownload })` — người làm Task 3 sửa trực tiếp trong cùng file, không tạo file mới.

---

### Task 3: Tải file + mở share sheet — sửa `frontend/app/(main)/tasks/[id].tsx`

**Files:**
- Modify: `frontend/app/(main)/tasks/[id].tsx`
- Modify: `frontend/package.json` (qua `npx expo install`)

**Interfaces:**
- Consumes: `fetchAttachmentBytes` (Task 1); `AttachmentRow`, `AttachmentsSection` (Task 2 — sửa trực tiếp trong file, xem "Ghi chú cho Task 3" ở cuối Task 2).

- [ ] **Step 1: Cài package `expo-file-system` và `expo-sharing`**

Run: `cd frontend && npx expo install expo-file-system expo-sharing`
Expected: cả 2 package xuất hiện trong `dependencies` của `frontend/package.json`.

- [ ] **Step 2: Tra docs Expo SDK 57 cho `expo-file-system` và `expo-sharing`**

Trước khi viết code, xem https://docs.expo.dev/versions/v57.0.0/sdk/filesystem/ và https://docs.expo.dev/versions/v57.0.0/sdk/sharing/. Plan này đã tra sẵn và ghi lại dưới đây — API hàm cũ (`FileSystem.writeAsStringAsync`, `FileSystem.cacheDirectory`) **đã deprecated, sẽ throw runtime**, KHÔNG dùng:
  - `Paths.cache` — `Directory` instance trỏ tới thư mục cache.
  - `new File(Paths.cache, filename)` — tạo `File` instance tại đường dẫn đó.
  - `file.create({ overwrite: true })` — tạo file, ghi đè nếu đã tồn tại (không truyền `overwrite: true` sẽ throw nếu file đã có — cần vì user có thể tải cùng 1 attachment nhiều lần).
  - `file.write(bytes)` — ghi `Uint8Array`/`ArrayBufferLike`/`string` vào file.
  - `file.uri` — chuỗi `file://...` để truyền cho `Sharing.shareAsync`.
  - `Sharing.isAvailableAsync()` — kiểm tra thiết bị có hỗ trợ share sheet không (web thường không).
  - `Sharing.shareAsync(url: string, options?)` — mở share sheet native cho file tại `url`.

- [ ] **Step 3: Sửa `AttachmentRow` trong `frontend/app/(main)/tasks/[id].tsx`**

Thay toàn bộ hàm `AttachmentRow` (viết ở Task 2) bằng:

```tsx
function AttachmentRow({
  a,
  downloading,
  onDownload,
}: {
  a: Attachment;
  downloading: boolean;
  onDownload: (a: Attachment) => void;
}) {
  return (
    <TouchableOpacity
      style={styles.row}
      onPress={() => onDownload(a)}
      disabled={downloading}
    >
      <View style={{ flex: 1 }}>
        <Text numberOfLines={1}>{a.original_filename}</Text>
        <Text style={{ color: colors.textSecondary }}>
          {formatFileSize(a.file_size)} — {new Date(a.created_at).toLocaleDateString("vi-VN")}
        </Text>
      </View>
      {downloading && <ActivityIndicator color={colors.primary} />}
    </TouchableOpacity>
  );
}
```

- [ ] **Step 4: Thêm import và tải file trong `AttachmentsSection`**

Thêm vào đầu file (cạnh các import khác):

```tsx
import { Alert } from "react-native"; // thêm Alert vào import react-native đã có ở Task 2
import * as Sharing from "expo-sharing";
import { File, Paths } from "expo-file-system";
import { fetchAttachmentBytes } from "../../../src/api/attachments"; // gộp vào dòng import attachments.ts đã có ở Task 2
```

(`Alert` gộp vào dòng `import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";` đã có sẵn từ Task 2 — thêm `Alert` vào danh sách đó, không tạo dòng import react-native thứ hai. Tương tự `fetchAttachmentBytes` gộp vào dòng `import { ATTACHMENT_MAX_SIZE, ATTACHMENT_MIME_TYPES, Attachment, listTaskAttachments, uploadTaskAttachment } from "../../../src/api/attachments";` đã có.)

Trong `AttachmentsSection`, thêm state và hàm tải file, và sửa phần render danh sách:

```tsx
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const handleDownload = async (a: Attachment) => {
    setDownloadingId(a.id);
    try {
      const bytes = await fetchAttachmentBytes(a.id);
      const file = new File(Paths.cache, `${a.id}_${a.original_filename}`);
      file.create({ overwrite: true });
      file.write(new Uint8Array(bytes));
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(file.uri);
      } else {
        Alert.alert("Thiết bị này không hỗ trợ chia sẻ file.");
      }
    } catch (e: any) {
      Alert.alert("Không tải được file", String(e?.message ?? e));
    } finally {
      setDownloadingId(null);
    }
  };
```

Sửa dòng render danh sách (cuối `AttachmentsSection`, trước đây gọi `<AttachmentRow key={a.id} a={a} />`):

```tsx
      {attachments?.map((a) => (
        <AttachmentRow
          key={a.id}
          a={a}
          downloading={downloadingId === a.id}
          onDownload={handleDownload}
        />
      ))}
```

- [ ] **Step 5: Xác minh bằng typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: không có output (0 lỗi).

- [ ] **Step 6: Commit**

```bash
git add frontend/app/\(main\)/tasks/\[id\].tsx frontend/package.json frontend/package-lock.json
git commit -m "feat(fe): tai file dinh kem ve va mo share sheet"
```

---

## Ghi chú

- Không có test tự động cho các task này (FE chưa có hạ tầng test) — `npx tsc --noEmit` là bước xác minh duy nhất bắt buộc agent chạy. Xác minh bằng mắt qua Expo dev server (`npm run start` từ `frontend/`) nên làm thủ công sau khi cả 3 task xong: upload 1 file hợp lệ → xuất hiện đầu danh sách; thử file quá 20MB → thấy đúng lỗi; bấm tải 1 file → share sheet mở, nội dung khớp file gốc; task chưa có file nào → thấy đúng empty state. Không bắt buộc agent tự chạy simulator.
- Web: `Sharing.isAvailableAsync()` có thể trả `false` trên web (theo docs SDK 57) — Task 3 đã xử lý bằng `Alert.alert` báo không hỗ trợ, không crash. Không cần xử lý thêm cho web trong plan này (app target chính là iOS/Android theo `funtional-plan.md` §9).
- Không có UI xóa attachment, không preview file nội bộ — cố ý theo spec FE §1, không thêm trong plan này.
