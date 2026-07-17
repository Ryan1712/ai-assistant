import { apiFetch } from "./client";

export type Comment = {
  id: string;
  task_id: string;
  author_id: string;
  author_name: string;
  content: string;
  created_at: string;
};

export const listComments = (taskId: string) =>
  apiFetch<Comment[]>(`/api/v1/tasks/${taskId}/comments`);

export const addComment = (taskId: string, content: string) =>
  apiFetch<Comment>(`/api/v1/tasks/${taskId}/comments`, {
    method: "POST",
    body: { content },
  });
