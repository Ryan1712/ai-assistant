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

export type TaskSummary = { id: string; title: string };

export const listTasks = () => apiFetch<TaskSummary[]>("/api/v1/tasks");
