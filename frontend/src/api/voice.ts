import fixWebmDuration from "fix-webm-duration";
import { Platform } from "react-native";
import { apiFetch, API_URL } from "./client";
import { getTokens } from "../auth/tokenStore";

export type VoiceNote = {
  id: string;
  transcript: string;
  language: string;
  transcript_status: "pending" | "queued" | "processing" | "done" | "failed";
  title: string | null;
  duration_seconds: number | null;
  tags: string[];
  task_id: string | null;
  project_id: string | null;
  created_at: string;
};

export const listVoiceNotes = (onDate?: string, tag?: string) => {
  const params = new URLSearchParams();
  if (onDate) params.set("on_date", onDate);
  if (tag) params.set("tag", tag);
  const qs = params.toString();
  return apiFetch<VoiceNote[]>(`/api/v1/voice-notes${qs ? `?${qs}` : ""}`);
};

export const deleteVoiceNote = (id: string) =>
  apiFetch<void>(`/api/v1/voice-notes/${id}`, { method: "DELETE" });

export const patchVoiceNote = (id: string, body: { title?: string; tags?: string[] }) =>
  apiFetch<VoiceNote>(`/api/v1/voice-notes/${id}`, { method: "PATCH", body });

export const retranscribeVoiceNote = (id: string) =>
  apiFetch<{ id: string; status: string }>(`/api/v1/voice-notes/${id}/transcribe`, {
    method: "POST",
  });

let _lastBlobUrl: string | null = null;

/** Audio source để phát ghi âm qua expo-audio (cần Bearer token vì endpoint yêu cầu đăng nhập). */
export async function voiceNoteAudioSource(id: string) {
  const url = `${API_URL}/api/v1/voice-notes/${id}/file`;
  const tokens = await getTokens();
  const headers = tokens?.access_token ? { Authorization: `Bearer ${tokens.access_token}` } : undefined;
  if (Platform.OS === "web") {
    // Thẻ <audio> trên web KHÔNG hỗ trợ header tùy chỉnh — {uri, headers} bị
    // bỏ qua, request tới /file thiếu Authorization nên bị từ chối, phát
    // lỗi "no supported source". Phải tự fetch kèm header rồi phát qua blob URL.
    const resp = await fetch(url, { headers });
    if (!resp.ok) throw new Error(`Không tải được file ghi âm (${resp.status})`);
    const blob = await resp.blob();
    if (_lastBlobUrl) URL.revokeObjectURL(_lastBlobUrl); // blob cũ không revoke = leak
    _lastBlobUrl = URL.createObjectURL(blob);
    return { uri: _lastBlobUrl };
  }
  return { uri: url, headers };
}

function extensionForMimeType(mimeType: string): string {
  if (mimeType.includes("webm")) return "webm";
  if (mimeType.includes("ogg")) return "ogg";
  if (mimeType.includes("wav")) return "wav";
  if (mimeType.includes("mp4") || mimeType.includes("m4a") || mimeType.includes("aac")) return "m4a";
  return "webm";
}

export const uploadVoiceNote = async (
  uri: string,
  opts: { durationMs?: number; tags?: string[]; title?: string } = {},
) => {
  const { durationMs, tags, title } = opts;
  const form = new FormData();
  if (Platform.OS === "web") {
    // Web: uri là blob: URL — {uri,name,type} kiểu RN bị FormData trình duyệt
    // serialize thành chuỗi "[object Object]", phải fetch ra Blob thật.
    const rawBlob = await (await fetch(uri)).blob();
    // Chrome MediaRecorder ghi webm KHÔNG kèm duration hợp lệ trong header
    // (bug quen thuộc) — nghe lại hiện thời lượng sai (vd 3s ra thành 2 phút).
    // durationMs (thời gian ghi thật, đo lúc còn đang ghi) dùng để vá lại.
    const blob = durationMs ? await fixWebmDuration(rawBlob, durationMs) : rawBlob;
    const ext = extensionForMimeType(blob.type || "audio/webm");
    form.append("file", blob, `note.${ext}`);
  } else {
    const base = uri.split("/").pop() ?? "";
    const name = /\.[a-z0-9]+$/i.test(base) ? base : "note.m4a";
    // RN FormData nhận {uri, name, type} cho file — cast vì DOM types không biết
    form.append("file", { uri, name, type: "audio/m4a" } as unknown as Blob);
  }
  if (tags && tags.length > 0) form.append("tags", tags.join(","));
  if (title) form.append("title", title);
  if (durationMs) form.append("duration_seconds", String(durationMs / 1000));
  return apiFetch<VoiceNote>("/api/v1/voice-notes", { method: "POST", body: form });
};
