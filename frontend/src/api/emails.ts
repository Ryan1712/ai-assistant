import { apiFetch } from "./client";

export type Email = {
  id: string;
  subject: string;
  body: string;
  counterpart_name: string;
  counterpart_email: string;
  task_id: string | null;
  project_id: string | null;
  created_at: string;
};

export const listEmails = (box: "inbox" | "sent") => {
  const params = new URLSearchParams();
  params.set("box", box);
  return apiFetch<Email[]>(`/api/v1/emails?${params.toString()}`);
};
