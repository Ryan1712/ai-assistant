/**
 * crashLogs.ts — gửi crash logs lên server bằng raw fetch (KHÔNG dùng apiFetch).
 *
 * ADR-002: endpoint crash-logs yêu cầu JWT; nếu chưa có token thì giữ lại hàng đợi
 *          và flush sau khi đăng nhập.
 * ADR-004: không bao giờ ném lỗi ra ngoài — luôn resolve.
 * Dùng global.fetch trực tiếp để tránh đệ quy: apiFetch lỗi → ghi log →
 * postCrashLogs gọi apiFetch → apiFetch lỗi → vòng lặp vô tận.
 */

import { getTokens } from "../auth/tokenStore";
import type { CrashPayload } from "../errors/types";

const API_URL =
  typeof process !== "undefined"
    ? (process.env.EXPO_PUBLIC_API_URL?.replace(/\/$/, "") ?? "")
    : "";
const CRASH_LOGS_ENDPOINT = `${API_URL}/api/v1/crash-logs`;

/**
 * Gửi danh sách crash payload lên server.
 *
 * @returns `sent` — có gửi được không; `shouldClear` — có thể xóa hàng đợi local không
 *
 * ADR-004: không ném lỗi — luôn resolve.
 */
export async function postCrashLogs(
  items: CrashPayload[],
): Promise<{ sent: boolean; shouldClear: boolean }> {
  try {
    const tokens = await getTokens();
    if (!tokens?.access_token) {
      // Chưa có token → giữ hàng đợi, flush sau khi đăng nhập
      return { sent: false, shouldClear: false };
    }

    const response = await (global.fetch as unknown as typeof fetch)(CRASH_LOGS_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${tokens.access_token}`,
      },
      body: JSON.stringify({ items }),
    });

    // Chỉ báo "có thể xóa" khi server xác nhận thành công; giữ lại để retry nếu lỗi
    return { sent: true, shouldClear: response.ok };
  } catch {
    // ADR-004: nuốt lỗi (mạng thất bại, token hỏng, fetch ném, v.v.)
    return { sent: false, shouldClear: false };
  }
}
