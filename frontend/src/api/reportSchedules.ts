import { apiFetch } from "./client";

export type ReportSchedule = {
  id: string;
  weekday: number | null; // 0=Thứ Hai..6=Chủ Nhật, null=hàng ngày
  hour: number;
  minute: number;
  project_id: string | null;
  assignee_id: string | null;
  status: string | null;
  recipient_id: string;
  active: boolean;
  last_run_at: string | null;
  next_run_at: string;
  created_at: string;
};

export const listReportSchedules = () => apiFetch<ReportSchedule[]>("/api/v1/report-schedules");

export const deleteReportSchedule = (id: string) =>
  apiFetch<void>(`/api/v1/report-schedules/${id}`, { method: "DELETE" });
