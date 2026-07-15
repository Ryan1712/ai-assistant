# Thiết kế FE — Đính kèm tài liệu trong task

**Ngày:** 2026-07-16 · **Trạng thái:** Đã duyệt qua brainstorming · **Spec BE liên quan:** [2026-07-15-task-attachments-design.md](2026-07-15-task-attachments-design.md)

BE (3 endpoint REST + tool chat `list_task_attachments`) đã xong. Spec này lấp phần FE mà BE spec cố ý tách ra: màn hình task detail hiển thị/tải/đính kèm tài liệu.

---

## 1. Phạm vi & Ranh giới

**Trong phạm vi:**
- 1 API module mới `frontend/src/api/attachments.ts` — types + gọi 3 endpoint BE đã có.
- 1 section mới "Tài liệu đính kèm" trong màn hình `frontend/app/(main)/tasks/[id].tsx` (list + upload + download), với 2 subcomponent cục bộ trong cùng file (đúng convention `ScheduleRow`/`QuickVoiceCard`).
- Chọn file bằng file picker chung (`expo-document-picker`), lọc sẵn theo MIME whitelist khớp BE.
- Tải file bằng `expo-file-system` (ghi vào cache, có Bearer token) + `expo-sharing` (mở share sheet native).
- Client-side pre-check dung lượng file (20MB) trước khi upload — fail fast, không tốn round-trip multipart cho file chắc chắn bị BE từ chối.

**Ngoài phạm vi (cố ý, YAGNI):**
- Không có UI xóa attachment (BE không có endpoint xóa).
- Không preview file trong app (PDF viewer, image viewer nội bộ) — dùng share sheet để mở bằng app khác trên máy, theo quyết định brainstorming.
- Không có màn hình "tất cả tài liệu" độc lập ngoài task detail — chỉ trong ngữ cảnh 1 task, đúng như BE model (`task_id` bắt buộc).
- Không có comment/thảo luận trong task — đó là tính năng khác (`TaskComment`), FE cho comment cũng chưa tồn tại, không thuộc phạm vi spec này.
- Không viết unit test mới — dự án FE hiện không có test framework (`package.json` không có script `test`, không file `*.test.ts` nào); verify bằng `tsc --noEmit` + chạy tay trên Expo dev server, đúng convention các plan FE trước (search-fe, report-schedules-fe).

**Lưu ý môi trường quan trọng cho người implement:** `frontend/AGENTS.md` ghi rõ "Expo HAS CHANGED — đọc docs đúng version tại https://docs.expo.dev/versions/v57.0.0/ trước khi viết code". Dự án dùng Expo `~57.0.4`. `expo-file-system` ở SDK gần đây (54+) đã đổi API sang class `File`/`Directory` (API cũ dạng hàm như `FileSystem.downloadAsync`/`FileSystem.writeAsStringAsync` có thể đã deprecated/thay đổi chữ ký) — **plan implementation phải tra đúng API hiện hành của `expo-file-system`, `expo-document-picker`, `expo-sharing` cho SDK 57 trước khi viết code**, không giả định theo API cũ từ training data.

---

## 2. API client mới — `frontend/src/api/attachments.ts`

Theo đúng pattern `voice.ts` (type phẳng + hàm mỏng bọc `apiFetch`):

```ts
import { apiFetch } from "./client";

export type Attachment = {
  id: string;
  task_id: string;
  author_id: string;
  original_filename: string;
  file_size: number;
  created_at: string;
};

export const listTaskAttachments = (taskId: string) =>
  apiFetch<Attachment[]>(`/api/v1/tasks/${taskId}/attachments`);

export const uploadTaskAttachment = (
  taskId: string,
  file: { uri: string; name: string; mimeType: string },
) => {
  const form = new FormData();
  form.append("file", { uri: file.uri, name: file.name, type: file.mimeType } as unknown as Blob);
  return apiFetch<Attachment>(`/api/v1/tasks/${taskId}/attachments`, {
    method: "POST",
    body: form,
  });
};
```

**Whitelist MIME cho file picker** (khớp 1-1 whitelist đuôi file bên BE — `_ALLOWED_EXTS` trong `backend/app/services/attachment_service.py`), khai báo trong cùng file `attachments.ts`:

```ts
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

export const ATTACHMENT_MAX_SIZE = 20 * 1024 * 1024; // 20MB — khớp backend/app/services/attachment_service.py _MAX_FILE_SIZE
```

**Download — KHÔNG dùng `apiFetch`.** `apiFetch` (`frontend/src/api/client.ts:43-76`) luôn parse `resp.json()` cho response 200 — endpoint `GET /api/v1/attachments/{id}/file` trả binary (`FileResponse` bên BE), không phải JSON, nên phải viết 1 hàm fetch riêng trong `attachments.ts`, tự lấy token qua `getTokens()` (từ `../auth/tokenStore`, cùng cách `client.ts` đang làm) và tự set header `Authorization`, không gọi `resp.json()`:

```ts
import { getTokens } from "../auth/tokenStore";
import { API_URL } from "./client";

export async function fetchAttachmentBytes(attachmentId: string): Promise<ArrayBuffer> {
  const tokens = await getTokens();
  const resp = await fetch(`${API_URL}/api/v1/attachments/${attachmentId}/file`, {
    headers: tokens?.access_token ? { Authorization: `Bearer ${tokens.access_token}` } : {},
  });
  if (!resp.ok) throw new Error(`download_failed_${resp.status}`);
  return resp.arrayBuffer();
}
```

Việc ghi bytes này vào cache + mở share sheet nằm ở tầng UI (mục 4), không phải trong `attachments.ts` — `attachments.ts` chỉ chịu trách nhiệm gọi API, không đụng filesystem (tách rõ trách nhiệm: API module vs UI/side-effect).

Người implement quyết định chữ ký chính xác của bước ghi file (`FileSystem`/`File` API của SDK 57) khi viết code, theo lưu ý ở mục 1.

---

## 3. Sửa `frontend/app/(main)/tasks/[id].tsx`

Thêm section mới ngay sau card thông tin task hiện tại (dòng 50, trước `)}`  đóng `{task && (...)}`), theo đúng layout `ScrollView` → nhiều `card` xếp chồng đã dùng ở `today.tsx`.

**2 subcomponent cục bộ mới trong cùng file** (không tách file riêng, đúng convention):

- `AttachmentRow({ a, onDownload, downloading })` — 1 dòng: tên file (`original_filename`) + dung lượng đã format (helper `formatFileSize(bytes)` — "245 KB"/"1.2 MB") + ngày tải lên (`toLocaleDateString("vi-VN")`, đúng cách task detail đang format deadline). Cả hàng là `TouchableOpacity` gọi `onDownload(a)`; hiện `ActivityIndicator` nhỏ thay vì text khi `downloading === a.id` (chỉ hàng đó bận, không khóa cả list).
- `AttachmentsSection({ taskId })` — tự quản lý state riêng (`attachments: Attachment[] | null`, `error`, `downloadingId`, `uploading`), fetch `listTaskAttachments(taskId)` trong `useEffect([taskId])`, render đủ 4 trạng thái, và nút "+ Đính kèm" ở header card.

**Nút "+ Đính kèm":** KHÔNG dùng `PrimaryButton` (component đó là nút block full-width cho form submit, không hợp với 1 action nhỏ trong header card) — dùng `TouchableOpacity` + `Text` cục bộ, cùng kiểu nhẹ như nút "Xóa" trong `ScheduleRow` (`report-schedules.tsx:59-61`), màu `colors.primary`, hiện `ActivityIndicator` nhỏ thay chữ khi `uploading === true`.

```tsx
function AttachmentsSection({ taskId }: { taskId: string }) {
  const [attachments, setAttachments] = useState<Attachment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  useEffect(() => {
    listTaskAttachments(taskId)
      .then(setAttachments)
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, [taskId]);

  const handlePick = async () => {
    // DocumentPicker.getDocumentAsync({ type: ATTACHMENT_MIME_TYPES }) — tra API SDK 57 chính xác khi code
    // check result.size > ATTACHMENT_MAX_SIZE -> setError sớm, không gọi upload
    // setUploading(true) -> uploadTaskAttachment -> unshift vào attachments -> setUploading(false)
  };

  const handleDownload = async (a: Attachment) => {
    // setDownloadingId(a.id) -> fetchAttachmentBytes -> ghi cache (File/Directory API SDK 57)
    // -> Sharing.shareAsync(localUri) -> setDownloadingId(null)
    // lỗi mạng/ghi file -> Alert.alert, không phải setError (không phải data-block state)
  };

  return (
    <View style={styles.card}>
      <View style={styles.sectionHeader}>
        <Text style={styles.cardTitle}>Tài liệu đính kèm</Text>
        <TouchableOpacity onPress={handlePick} disabled={uploading}>
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
        <AttachmentRow
          key={a.id}
          a={a}
          downloading={downloadingId === a.id}
          onDownload={handleDownload}
        />
      ))}
    </View>
  );
}
```

(Code trên minh họa cấu trúc/state — comment thay cho phần gọi `DocumentPicker`/`FileSystem`/`Sharing` cụ thể, vì chữ ký chính xác phụ thuộc API SDK 57 mà người implement phải tra trước, theo lưu ý mục 1.)

---

## 4. Package mới cần thêm vào `frontend/package.json`

- `expo-document-picker` — chọn file từ máy.
- `expo-file-system` — ghi bytes tải về vào cache.
- `expo-sharing` — mở share sheet native.

Cài bằng `npx expo install expo-document-picker expo-file-system expo-sharing` (từ `frontend/`) để Expo tự chọn đúng version khớp SDK 57 — không tự ghi version tay vào `package.json`.

---

## 5. Trạng thái & lỗi (theo `DESIGN.md` — 4 trạng thái bắt buộc mỗi khối dữ liệu)

| Trạng thái | Hiển thị |
|---|---|
| Loading (list) | `ActivityIndicator` khi `attachments === null` |
| Empty | Text `textMuted` "Chưa có tài liệu nào — bấm + Đính kèm để thêm" |
| Error (list/upload) | `ErrorText` dùng chung, hiện dưới header card — lỗi upload không che mất list đã tải trước đó |
| Data | Danh sách `AttachmentRow` |

**Lỗi cụ thể khi upload:**
- File > 20MB chọn từ picker → chặn client-side trước khi gọi API, hiện luôn "File vượt quá 20MB." (không tốn round-trip).
- BE trả `422 unsupported_file_format` (hiếm, vì đã lọc MIME ở picker, nhưng OS có thể báo sai MIME) → "Định dạng file không được hỗ trợ."
- BE trả `422 file_too_large` (dự phòng nếu check client-side lệch) → "File vượt quá 20MB."
- `404` (task không còn thấy được — hiếm vì đang đứng trong màn hình task đó) → dùng message lỗi chung từ `ApiError`.

**Lỗi khi download:** không phải data-block nên không dùng `ErrorText` — dùng `Alert.alert("Không tải được file", ...)`, đơn giản, không chặn thao tác khác trên màn hình.

**Phản hồi thành công (peak-end, theo `DESIGN.md`):** upload xong → file mới xuất hiện ngay đầu danh sách (không cần toast riêng, phản hồi tức thời qua UI); tải file xong → share sheet tự mở là phản hồi rõ ràng có sẵn, không cần thêm gì.

---

## 6. Testing / Verification

Không viết unit test (dự án FE không có test framework, xem mục 1). Verify bằng:
- `tsc --noEmit` sạch sau mỗi bước code.
- Chạy tay trên Expo dev server (`npm run start` từ `frontend/`):
  - Upload 1 file hợp lệ (vd. `.pdf`) → xuất hiện đầu danh sách.
  - Thử chọn file bị whitelist chặn từ picker (nếu OS cho chọn ngoài whitelist) hoặc file > 20MB → thấy đúng message lỗi, không crash.
  - Bấm tải 1 file đã có → share sheet mở, nội dung file đúng (so khớp với file gốc đã upload).
  - Task chưa có file nào → thấy đúng empty state.
  - Nhiều file (>3) → list hiển thị đúng thứ tự mới nhất trước (khớp thứ tự BE trả về).

---

## Self-review (đã chạy)

- **Placeholder scan:** không có TBD mơ hồ; whitelist MIME, giới hạn 20MB, package cần thêm đã chốt cụ thể. Phần code minh họa `handlePick`/`handleDownload` cố ý để dạng comment vì phụ thuộc API SDK 57 cụ thể (đã giải thích lý do rõ ràng ở mục 1 và mục 3, không phải "để sau" mơ hồ).
- **Nhất quán nội bộ:** `attachments.ts` chỉ gọi API (không đụng filesystem); phần ghi file + share sheet nằm ở tầng UI trong `[id].tsx` — tách trách nhiệm rõ, khớp nguyên tắc "mỗi file 1 trách nhiệm" của brainstorming skill.
- **Phạm vi:** đủ nhỏ cho 1 implementation plan — ước lượng 2-3 task (API module + package, section UI list+upload, download+share). Không đụng comment/thảo luận (tính năng khác, không thuộc §8 phần này).
- **Ambiguity check:** đã chốt rõ "file picker chung + lọc MIME sẵn" (không phải chỉ ảnh), "tải về + share sheet" (không phải preview nội bộ), "không dùng `PrimaryButton` cho nút + Đính kèm" — không còn chỗ hiểu 2 nghĩa. Điểm duy nhất cố ý để người implement tự tra cứu là **API chính xác của `expo-file-system`/`expo-document-picker`/`expo-sharing` cho Expo SDK 57** — đây là rủi ro thật (API các package này đổi giữa các SDK) nên không thể chốt cứng trong spec mà không tra docs tại thời điểm code, đã nói rõ lý do và cảnh báo ở mục 1.
