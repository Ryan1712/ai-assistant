/**
 * breadcrumbs.ts — ring buffer 20 mục ghi vết điều hướng / sự kiện trước khi crash.
 * Giúp tái hiện ngữ cảnh dẫn đến sự cố.
 */

/** Một breadcrumb ghi nhận một sự kiện */
export interface Breadcrumb {
  type: "nav" | "api" | "user" | "info";
  message: string;
  timestamp: string;
}

const BUFFER_SIZE = 20;
// Buffer trong bộ nhớ — đủ đơn giản, không cần AsyncStorage (breadcrumb chỉ sống trong phiên)
const buffer: Breadcrumb[] = [];

/**
 * Thêm một breadcrumb vào ring buffer.
 * Tự bỏ mục cũ nhất khi buffer đầy (hơn 20 mục).
 */
export function addBreadcrumb(crumb: Breadcrumb): void {
  buffer.push(crumb);
  if (buffer.length > BUFFER_SIZE) {
    buffer.shift(); // bỏ mục cũ nhất (FIFO)
  }
}

/**
 * Lấy bản sao của toàn bộ breadcrumb hiện tại.
 * Mục mới nhất ở cuối mảng.
 */
export function getBreadcrumbs(): Breadcrumb[] {
  return [...buffer];
}

/**
 * Xóa toàn bộ breadcrumb (dùng khi đăng xuất hoặc bắt đầu phiên mới).
 */
export function clearBreadcrumbs(): void {
  buffer.length = 0;
}
