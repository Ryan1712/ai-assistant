import { apiFetch } from "./client";

export type VoiceNote = {
  id: string;
  transcript: string;
  language: string;
  tags: string[];
  task_id: string | null;
  project_id: string | null;
  created_at: string;
};

export const listVoiceNotes = (onDate?: string) =>
  apiFetch<VoiceNote[]>(`/api/v1/voice-notes${onDate ? `?on_date=${onDate}` : ""}`);

export const uploadVoiceNote = (uri: string) => {
  const base = uri.split("/").pop() ?? "";
  const name = /\.[a-z0-9]+$/i.test(base) ? base : "note.m4a";
  const form = new FormData();
  // RN FormData nhận {uri, name, type} cho file — cast vì DOM types không biết
  form.append("file", { uri, name, type: "audio/m4a" } as unknown as Blob);
  return apiFetch<VoiceNote>("/api/v1/voice-notes", { method: "POST", body: form });
};
