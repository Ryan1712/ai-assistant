/**
 * index.ts — barrel export cho hệ thống báo cáo sự cố.
 * Import từ đây để dùng trong app (App.tsx, navigators, AuthContext...).
 */

// Kiểu dữ liệu
export type { CrashPayload, CrashSource, CrashSeverity } from "./types";

// Hàng đợi crash
export { report, flush, getQueue, clearQueue } from "./crashReporter";

// Công cụ
export { computeFingerprint } from "./fingerprint";
export { redact } from "./redact";
export { getDeviceInfo } from "./deviceInfo";
export type { DeviceInfo } from "./deviceInfo";

// Breadcrumbs
export { addBreadcrumb, getBreadcrumbs, clearBreadcrumbs } from "./breadcrumbs";
export type { Breadcrumb } from "./breadcrumbs";

// Khởi tạo dịch vụ
export { initGlobalHandlers } from "./globalHandlers";
export { initSessionSentinel, updateLastScreen, getCurrentScreen } from "./sessionSentinel";
export { initSentry } from "./sentry";

// Components
export { ErrorBoundary } from "./ErrorBoundary";
export { ScreenErrorBoundary, makeScreen } from "./ScreenErrorBoundary";
