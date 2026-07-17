import { apiFetch } from "./client";

export type Notification = {
  id: string;
  type: string;
  payload: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
};

export const listNotifications = (unreadOnly = false) =>
  apiFetch<Notification[]>(`/api/v1/notifications${unreadOnly ? "?unread_only=true" : ""}`);

export const markNotificationRead = (id: string) =>
  apiFetch<void>(`/api/v1/notifications/${id}/read`, { method: "POST" });

export const markAllNotificationsRead = () =>
  apiFetch<void>("/api/v1/notifications/read-all", { method: "POST" });

export const getNotificationPreferences = () =>
  apiFetch<Record<string, boolean>>("/api/v1/notifications/preferences");

export const setNotificationPreference = (type: string, enabled: boolean) =>
  apiFetch<Record<string, boolean>>("/api/v1/notifications/preferences", {
    method: "PATCH",
    body: { type, enabled },
  });
