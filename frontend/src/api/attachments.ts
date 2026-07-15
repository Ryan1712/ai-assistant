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
