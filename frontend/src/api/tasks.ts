import { apiFetch } from "./client";

export type TaskDetail = {
  id: string;
  project_id: string;
  title: string;
  description: string;
  status: string;
  percent: number;
  deadline: string | null;
  priority: string;
  assignee_ids: string[];
};

export const getTask = (id: string) => apiFetch<TaskDetail>(`/api/v1/tasks/${id}`);

export const listTasks = () => apiFetch<TaskDetail[]>("/api/v1/tasks");

export const deleteTask = (id: string) =>
  apiFetch<void>(`/api/v1/tasks/${id}`, { method: "DELETE" });
