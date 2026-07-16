import { apiFetch } from "./client";

export type AuditEvent = {
  type: "task_update" | "login" | "instruction_edit" | "skill_edit" | "account_event";
  actor_id: string;
  actor_name: string;
  summary: string;
  created_at: string;
  target_user_id?: string;
  target_name?: string;
};

export const listAuditEvents = (dateFrom?: string, dateTo?: string) => {
  const params = new URLSearchParams();
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);
  const qs = params.toString();
  return apiFetch<AuditEvent[]>(`/api/v1/audit-events${qs ? `?${qs}` : ""}`);
};
