import { apiFetch } from "./client";

export type DashTask = {
  id: string;
  title: string;
  status: string;
  percent: number;
  priority: string;
  deadline: string | null;
};

export type TodayDashboard = {
  due_today: DashTask[];
  overdue: DashTask[];
  in_progress: DashTask[];
  recent_updates: {
    task_id: string;
    task_title: string;
    author: string;
    content: string;
    percent: number | null;
    created_at: string;
  }[];
  notes_today: { id: string; content: string; tags: string[] }[];
  counters: { overdue: number; waiting_on_me: number; updates_24h: number };
};

export const getTodayDashboard = () => apiFetch<TodayDashboard>("/api/v1/dashboard/today");

export type Subscription = { plan: "basic" | "advanced"; limits: Record<string, number> | null };

export const getSubscription = () => apiFetch<Subscription>("/api/v1/subscription");

export const switchPlan = (plan: "basic" | "advanced") =>
  apiFetch<Subscription>("/api/v1/subscription", { method: "PATCH", body: { plan } });

export const getInviteCode = () =>
  apiFetch<{ invite_code: string }>("/api/v1/workspace/invite-code");
