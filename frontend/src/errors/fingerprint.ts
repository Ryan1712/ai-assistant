/**
 * fingerprint.ts — tính fingerprint ổn định từ source + message + stack.
 * Hàm thuần (pure function): cùng input → cùng output, không phụ thuộc ngoại cảnh.
 * Kết quả dùng để nhóm crash giống nhau và dedup hàng đợi.
 */

import type { CrashSource } from "./types";

/** Chuẩn hoá chuỗi: bỏ địa chỉ bộ nhớ và số dòng để hash ổn định hơn giữa các build. */
function normalize(s: string): string {
  return s
    .replace(/0x[0-9a-fA-F]+/g, "0xXXX") // địa chỉ bộ nhớ hex
    .replace(/:\d+:\d+/g, ":N:N")         // số dòng:cột trong stack trace
    .slice(0, 500);                        // giới hạn độ dài để hash nhất quán
}

/** djb2 hash — đơn giản, ổn định, phù hợp dedup crash không cần bảo mật. */
function djb2(str: string): number {
  let hash = 5381;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash) ^ str.charCodeAt(i);
    hash = hash | 0; // ép 32-bit signed int
  }
  return hash >>> 0; // chuyển sang unsigned để không âm
}

/**
 * Tính fingerprint 8 ký tự hex từ source + message + stack (tùy chọn).
 *
 * @param source - Nguồn crash (fe_js, fe_boundary, v.v.)
 * @param message - Thông báo lỗi
 * @param stack - Stack trace (tùy chọn)
 * @returns Chuỗi hex 8 ký tự, ví dụ "a3f2b1c4"
 */
export function computeFingerprint(
  source: CrashSource | string,
  message: string,
  stack?: string,
): string {
  const input = `${source}|${normalize(message)}|${stack ? normalize(stack) : ""}`;
  return djb2(input).toString(16).padStart(8, "0");
}
