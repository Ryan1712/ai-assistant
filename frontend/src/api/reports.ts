import { API_URL, apiFetch } from "./client";
import { getTokens } from "../auth/tokenStore";

export type Report = {
  id: string;
  kind: string;
  filters: Record<string, unknown>;
  summary: Record<string, unknown>;
  created_at: string;
};

export const listReports = () => apiFetch<Report[]>("/api/v1/reports");

export const fetchReportBytes = async (reportId: string): Promise<ArrayBuffer> => {
  const tokens = await getTokens();
  const resp = await fetch(`${API_URL}/api/v1/reports/${reportId}/download`, {
    headers: tokens?.access_token ? { Authorization: `Bearer ${tokens.access_token}` } : {},
  });
  if (!resp.ok) throw new Error(`download_failed_${resp.status}`);
  return resp.arrayBuffer();
};
