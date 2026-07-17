import { apiFetch } from "./client";

export type Note = {
  id: string;
  content: string;
  tags: string[];
  note_date: string;
  task_id: string | null;
  project_id: string | null;
};

export const listNotes = (params?: { onDate?: string; tag?: string }) => {
  const qs = new URLSearchParams();
  if (params?.onDate) qs.set("on_date", params.onDate);
  if (params?.tag) qs.set("tag", params.tag);
  const query = qs.toString();
  return apiFetch<Note[]>(`/api/v1/notes${query ? `?${query}` : ""}`);
};

export const createNote = (body: { content: string; tags?: string[]; note_date?: string }) =>
  apiFetch<Note>("/api/v1/notes", { method: "POST", body });
