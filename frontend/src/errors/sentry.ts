/**
 * sentry.ts — khởi tạo Sentry cho báo cáo sự cố.
 *
 * ADR-003: không làm gì và không cảnh báo khi EXPO_PUBLIC_SENTRY_DSN không được cấu hình.
 * Import @sentry/react-native qua dynamic import để tránh crash native module trong test.
 */

const DSN =
  typeof process !== "undefined"
    ? (process.env.EXPO_PUBLIC_SENTRY_DSN ?? "")
    : "";

/**
 * Khởi tạo Sentry.
 * Tự động no-op (không làm gì, không cảnh báo) nếu DSN chưa được cấu hình.
 */
export async function initSentry(): Promise<void> {
  if (!DSN) return; // ADR-003: im lặng khi thiếu DSN

  try {
    // Import động để tránh lỗi native module trong môi trường Jest
    const Sentry = await import("@sentry/react-native");
    Sentry.init({
      dsn: DSN,
      tracesSampleRate: 0.1,
      // eslint-disable-next-line no-undef
      environment: __DEV__ ? "development" : "production",
    });
  } catch {
    // Môi trường không hỗ trợ Sentry (test, CI không có native) — bỏ qua
  }
}
