import { apiFetch } from "./client";

export type Project = {
  id: string;
  name: string;
  goal: string;
  status: string;
  deadline: string | null;
  owner_id: string | null;
};

export const listProjects = () => apiFetch<Project[]>("/api/v1/projects");
