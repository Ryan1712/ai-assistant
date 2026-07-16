import { apiFetch } from "./client";

export type TeamUser = {
  id: string;
  email: string;
  full_name: string;
  role: "ceo" | "manager" | "employee";
  is_root: boolean;
  manager_id: string | null;
  status: "active" | "locked";
};

export type OffboardResult = {
  locked: boolean;
  successor_id: string | null;
  tasks_reassigned: number;
  projects_reassigned: number;
  reports_reassigned: number;
};

export type ChangeRoleResult = {
  role: string;
  manager_id: string | null;
  successor_id: string | null;
  reports_reassigned: number;
  projects_reassigned: number;
};

export const listUsers = () => apiFetch<TeamUser[]>("/api/v1/users");

export const lockUser = (id: string) =>
  apiFetch<void>(`/api/v1/users/${id}/lock`, { method: "POST" });

export const unlockUser = (id: string) =>
  apiFetch<void>(`/api/v1/users/${id}/unlock`, { method: "POST" });

export const offboardUser = (id: string, successorId?: string) =>
  apiFetch<OffboardResult>(`/api/v1/users/${id}/offboard`, {
    method: "POST",
    body: successorId ? { successor_id: successorId } : {},
  });

export const changeRole = (
  id: string,
  body: { new_role?: string; new_manager_id?: string; successor_id?: string },
) => apiFetch<ChangeRoleResult>(`/api/v1/users/${id}/change-role`, { method: "POST", body });
