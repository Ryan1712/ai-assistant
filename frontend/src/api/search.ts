import { apiFetch } from "./client";

export type SearchTask = { id: string; title: string; status: string; project_id: string };
export type SearchNote = { id: string; content: string; note_date: string };
export type SearchVoiceNote = { id: string; transcript: string; created_at: string };
export type SearchUser = { id: string; full_name: string; email: string; role: string };
export type SearchSkill = { id: string; name: string; kind: string };

export type SearchResult = {
  tasks: SearchTask[];
  notes: SearchNote[];
  voice_notes: SearchVoiceNote[];
  users: SearchUser[];
  skills: SearchSkill[];
};

export const searchAll = (q: string) =>
  apiFetch<SearchResult>(`/api/v1/search?q=${encodeURIComponent(q)}`);
