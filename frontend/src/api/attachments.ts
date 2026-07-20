import { File, UploadType } from "expo-file-system";
import { Platform } from "react-native";
import { ApiError, API_URL, apiFetch } from "./client";
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

export const uploadTaskAttachment = async (
  taskId: string,
  file: { uri: string; name: string; mimeType: string },
) => {
  if (Platform.OS === "web") {
    const form = new FormData();
    // Web: uri là blob: URL — {uri,name,type} kiểu RN bị FormData trình duyệt
    // serialize thành chuỗi "[object Object]", phải fetch ra Blob thật.
    const blob = await (await fetch(file.uri)).blob();
    form.append("file", blob, file.name);
    return apiFetch<Attachment>(`/api/v1/tasks/${taskId}/attachments`, {
      method: "POST",
      body: form,
    });
  }

  // Native: fetch() global của Expo (winter/fetch) không hỗ trợ kiểu FormData
  // part {uri,name,type} truyền thống của RN nữa — ném "Unsupported
  // FormDataPart implementation". Dùng thẳng File.upload() của expo-file-system.
  const tokens = await getTokens();
  const result = await new File(file.uri).upload(
    `${API_URL}/api/v1/tasks/${taskId}/attachments`,
    {
      uploadType: UploadType.MULTIPART,
      fieldName: "file",
      mimeType: file.mimeType,
      headers: tokens?.access_token ? { Authorization: `Bearer ${tokens.access_token}` } : undefined,
    },
  );
  if (result.status < 200 || result.status >= 300) {
    let detail: unknown = result.body;
    try {
      detail = JSON.parse(result.body).detail ?? detail;
    } catch {}
    throw new ApiError(result.status, detail);
  }
  return JSON.parse(result.body) as Attachment;
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
