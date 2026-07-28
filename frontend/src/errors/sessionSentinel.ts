/**
 * sessionSentinel.ts — theo dõi phiên làm việc: màn hình hiện tại, trạng thái app.
 * Ghi breadcrumb khi app chuyển foreground/background để cung cấp ngữ cảnh trước crash.
 */

import { AppState, type AppStateStatus } from "react-native";
import { addBreadcrumb } from "./breadcrumbs";

let currentScreen = "Unknown";
let sentinelInitialized = false;

/**
 * Cập nhật màn hình hiện tại và ghi breadcrumb điều hướng.
 * Gọi từ navigator mỗi khi màn hình thay đổi.
 */
export function updateLastScreen(screenName: string): void {
  currentScreen = screenName;
  addBreadcrumb({
    type: "nav",
    message: `nav:${screenName}`,
    timestamp: new Date().toISOString(),
  });
}

/** Lấy tên màn hình đang hiển thị (dùng khi tạo crash payload). */
export function getCurrentScreen(): string {
  return currentScreen;
}

/**
 * Khởi tạo sentinel theo dõi trạng thái app (foreground/background/inactive).
 * Gọi một lần khi app khởi động. Bọc try/catch — không bao giờ ném lỗi.
 */
export function initSessionSentinel(): void {
  if (sentinelInitialized) return;
  sentinelInitialized = true;

  try {
    const handleAppStateChange = (nextState: AppStateStatus) => {
      addBreadcrumb({
        type: "info",
        message: `app:${nextState}`,
        timestamp: new Date().toISOString(),
      });
    };

    AppState.addEventListener("change", handleAppStateChange);
  } catch {
    // Không ném lỗi nếu AppState không khả dụng (môi trường test)
  }
}
