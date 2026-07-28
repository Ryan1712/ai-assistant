/**
 * redact.ts — lọc dữ liệu nhạy cảm khỏi context trước khi gửi báo cáo sự cố.
 * Xóa các key nhạy cảm (Authorization, password, v.v.) và sanitize Bearer token
 * trong giá trị chuỗi.
 */

/** Tập hợp tên trường nhạy cảm (so sánh không phân biệt hoa thường) */
const SENSITIVE_KEYS: ReadonlySet<string> = new Set([
  "authorization",
  "refresh_token",
  "access_token",
  "password",
]);

/**
 * Regex tìm Bearer token trong chuỗi.
 * Khớp "Bearer" theo sau bởi ký tự không phải khoảng trắng (token liền hoặc qua dấu =/-).
 */
const BEARER_REGEX = /Bearer\S*/g;

/** Sanitize giá trị: xóa Bearer token từ chuỗi, đệ quy vào object/array. */
function sanitizeValue(value: unknown): unknown {
  if (typeof value === "string") {
    return value.replace(BEARER_REGEX, "[REDACTED]");
  }
  if (Array.isArray(value)) {
    return value.map(sanitizeValue);
  }
  if (value !== null && typeof value === "object") {
    return redact(value);
  }
  return value;
}

/**
 * Lọc object context: xóa key nhạy cảm và sanitize Bearer token trong giá trị chuỗi.
 * An toàn với null/undefined — trả về object rỗng thay vì ném lỗi.
 *
 * @param obj - Object cần lọc
 * @returns Object đã lọc, không chứa dữ liệu nhạy cảm
 */
export function redact(obj: unknown): Record<string, unknown> {
  if (
    obj === null ||
    obj === undefined ||
    typeof obj !== "object" ||
    Array.isArray(obj)
  ) {
    return {};
  }

  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj as Record<string, unknown>)) {
    // Bỏ qua key nhạy cảm
    if (SENSITIVE_KEYS.has(key.toLowerCase())) {
      continue;
    }
    result[key] = sanitizeValue(value);
  }
  return result;
}
