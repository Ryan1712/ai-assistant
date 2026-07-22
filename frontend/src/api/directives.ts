import { apiFetch } from "./client";

export type DirectiveStatus =
  | "sent"
  | "seen"
  | "acked"
  | "question"
  | "renegotiate"
  | "done"
  | "cancelled";

export type Directive = {
  id: string;
  created_by: string;
  recipient_id: string;
  task_id: string | null;
  verbatim_text: string;
  structured_summary: string;
  deadline: string | null;
  status: DirectiveStatus;
  response_text: string | null;
  created_at: string;
};

export const listDirectives = () => apiFetch<Directive[]>("/api/v1/directives");

export const ackDirective = (id: string) =>
  apiFetch<Directive>(`/api/v1/directives/${id}/ack`, { method: "POST" });

export const raiseDirectiveQuestion = (id: string, questionText: string) =>
  apiFetch<Directive>(`/api/v1/directives/${id}/question`, {
    method: "POST",
    body: { question_text: questionText },
  });

export const renegotiateDirective = (id: string, reason: string) =>
  apiFetch<Directive>(`/api/v1/directives/${id}/renegotiate`, {
    method: "POST",
    body: { reason },
  });
