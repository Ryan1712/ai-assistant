import { apiFetch } from "./client";

// Khớp backend/app/services/portal_service.py PortalReport — data là dict tự do,
// hình dạng khác nhau theo từng báo cáo (số liệu doanh thu, vận hành...).
export type PortalReport = {
  id: string;
  title: string;
  period: string;
  summary: string;
  data: Record<string, unknown>;
};

export const listPortalReports = () => apiFetch<PortalReport[]>("/api/v1/portal/reports");

export const getPortalReport = (id: string) =>
  apiFetch<PortalReport>(`/api/v1/portal/reports/${id}`);
