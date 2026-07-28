/**
 * globalHandlers.ts — đặt handler toàn cục cho lỗi JS và promise rejection.
 * Dùng ErrorUtils (React Native) thay cho window.onerror (không có trong RN).
 * Không bao giờ ném lỗi ra ngoài.
 */

import { report } from "./crashReporter";
import { computeFingerprint } from "./fingerprint";

// Khai báo kiểu ErrorUtils (RN global, không có trong @types/react-native mặc định)
type ErrorHandler = (error: Error, isFatal?: boolean) => void;
type ErrorUtilsStatic = {
  setGlobalHandler: (handler: ErrorHandler) => void;
  getGlobalHandler?: () => ErrorHandler | null;
};

function generateEventId(): string {
  return `geh-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/**
 * Khởi tạo handler bắt lỗi JS toàn cục và promise rejection chưa xử lý.
 * Gọi một lần khi app khởi động (trước khi render bất kỳ component nào).
 */
export function initGlobalHandlers(): void {
  // ─── Bắt lỗi JS qua ErrorUtils (RN-specific) ──────────────────────────────
  const errorUtils = (global as unknown as { ErrorUtils?: ErrorUtilsStatic }).ErrorUtils;
  if (errorUtils) {
    const originalHandler = errorUtils.getGlobalHandler?.() ?? null;

    errorUtils.setGlobalHandler((error: Error, isFatal?: boolean) => {
      const fingerprint = computeFingerprint(
        "fe_js",
        error?.message ?? "Lỗi không xác định",
        error?.stack,
      );

      // Ghi vào hàng đợi không đồng bộ (handler đồng bộ không await được)
      report({
        source: "fe_js",
        severity: isFatal ? "fatal" : "error",
        message: error?.message ?? "Lỗi không xác định",
        stack: error?.stack,
        fingerprint,
        occurred_at: new Date().toISOString(),
        client_event_id: generateEventId(),
      }).catch(() => {});

      // Chuyển tiếp cho handler gốc của RN (log lên Metro, v.v.)
      if (originalHandler) {
        originalHandler(error, isFatal);
      }
    });
  }

  // ─── Bắt promise rejection chưa xử lý (Hermes engine) ────────────────────
  if (typeof process !== "undefined" && typeof process.on === "function") {
    process.on("unhandledRejection", (reason: unknown) => {
      const error =
        reason instanceof Error
          ? reason
          : new Error(String(reason ?? "Lỗi không xác định"));

      const fingerprint = computeFingerprint("fe_promise", error.message, error.stack);

      report({
        source: "fe_promise",
        severity: "error",
        message: `Unhandled Promise Rejection: ${error.message}`,
        stack: error.stack,
        fingerprint,
        occurred_at: new Date().toISOString(),
        client_event_id: generateEventId(),
      }).catch(() => {});
    });
  }
}
