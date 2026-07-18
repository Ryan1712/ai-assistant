import { apiFetch, API_URL } from "./client";
import { getTokens } from "../auth/tokenStore";

export type VoiceNote = {
  id: string;
  transcript: string;
  language: string;
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

/** Audio source (uri + header xác thực) để phát ghi âm qua expo-audio. */
export async function voiceNoteAudioSource(id: string) {
  const tokens = await getTokens();
  return {
    uri: `${API_URL}/api/v1/voice-notes/${id}/file`,
    headers: tokens?.access_token ? { Authorization: `Bearer ${tokens.access_token}` } : undefined,
  };
}

export const uploadVoiceNote = (uri: string) => {
  const base = uri.split("/").pop() ?? "";
  const name = /\.[a-z0-9]+$/i.test(base) ? base : "note.m4a";
  const form = new FormData();
  // RN FormData nhận {uri, name, type} cho file — cast vì DOM types không biết
  form.append("file", { uri, name, type: "audio/m4a" } as unknown as Blob);
  return apiFetch<VoiceNote>("/api/v1/voice-notes", { method: "POST", body: form });
};
