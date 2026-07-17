import { apiFetch } from "./client";

export type Instruction = {
  id: string;
  title: string;
  version: number;
  content: string;
};

export const listInstructions = () => apiFetch<Instruction[]>("/api/v1/instructions");

export const createInstruction = (body: { title: string; content: string }) =>
  apiFetch<Instruction>("/api/v1/instructions", { method: "POST", body });

export const updateInstruction = (id: string, content: string) =>
  apiFetch<{ id: string; version: number }>(`/api/v1/instructions/${id}`, {
    method: "PATCH",
    body: { content },
  });

export const deleteInstruction = (id: string) =>
  apiFetch<void>(`/api/v1/instructions/${id}`, { method: "DELETE" });
