import { apiFetch } from "./client";

export type SkillKind = "profile" | "knowledge";

export type Skill = {
  id: string;
  name: string;
  kind: SkillKind;
  task_id: string | null;
  latest_version: number;
};

export type TaskUpdateSummary = {
  author_id: string;
  content: string;
  percent: number | null;
  created_at: string;
};

export type TaskState = {
  id: string;
  title: string;
  status: string;
  percent: number;
  deadline: string | null;
  priority: string;
  assignees: string[];
  latest_updates: TaskUpdateSummary[];
};

export type SkillDetail = {
  skill_id: string;
  name: string;
  kind: SkillKind;
  version: number;
  content: string;
  task_state: TaskState | null;
};

export const listSkills = () => apiFetch<Skill[]>("/api/v1/skills");

export const createSkill = (body: {
  name: string;
  kind: SkillKind;
  task_id?: string;
  content: string;
}) => apiFetch<Skill>("/api/v1/skills", { method: "POST", body });

export const addSkillVersion = (id: string, content: string) =>
  apiFetch<{ version: number }>(`/api/v1/skills/${id}/versions`, {
    method: "POST",
    body: { content },
  });

export const grantSkill = (id: string, userId: string) =>
  apiFetch<void>(`/api/v1/skills/${id}/grants`, {
    method: "POST",
    body: { user_id: userId },
  });

export type SkillGrant = { user_id: string; full_name: string };

export const listSkillGrants = (id: string) =>
  apiFetch<SkillGrant[]>(`/api/v1/skills/${id}/grants`);

export const revokeSkillGrant = (id: string, userId: string) =>
  apiFetch<void>(`/api/v1/skills/${id}/grants/${userId}`, { method: "DELETE" });

export const useSkill = (id: string) => apiFetch<SkillDetail>(`/api/v1/skills/${id}/use`);
