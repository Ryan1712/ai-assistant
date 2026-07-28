/**
 * types.ts — kiểu dữ liệu cốt lõi cho hệ thống báo cáo sự cố.
 * Các kiểu này khớp với schema bảng crash_logs ở backend.
 */

/** Nguồn phát sinh crash */
export type CrashSource = "fe_js" | "fe_promise" | "fe_boundary" | "fe_network";

/** Mức độ nghiêm trọng */
export type CrashSeverity = "fatal" | "error" | "warning" | "info";

/** Cấu trúc payload gửi lên server — khớp với crash_logs schema */
export interface CrashPayload {
  // Trường bắt buộc
  source: CrashSource;
  severity: CrashSeverity;
  message: string;
  fingerprint: string;
  occurred_at: string;
  client_event_id: string;

  // Trường tùy chọn
  stack?: string;
  component_stack?: string;
  screen?: string;
  app_version?: string;
  build_number?: string;
  platform?: string;
  os_version?: string;
  device_model?: string;
  is_device?: boolean;
  request_method?: string;
  request_path?: string;
  response_status?: number;
  context?: Record<string, unknown>;
}
