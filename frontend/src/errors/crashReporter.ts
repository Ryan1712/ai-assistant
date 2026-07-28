/**
 * crashReporter.ts — hàng đợi crash offline và gửi batch khi có kết nối.
 *
 * ADR-004: MỌI hàm public bọc try/catch nuốt lỗi — không bao giờ ném ra ngoài.
 * ADR-002: flush() gọi global.fetch trực tiếp (không qua apiFetch) để tránh đệ quy log.
 * Tối đa 50 bản ghi (FIFO), dedup theo cặp (fingerprint, hash_nội_dung).
 */

import AsyncStorage from "@react-native-async-storage/async-storage";
import { computeFingerprint } from "./fingerprint";
import type { CrashPayload } from "./types";

// ─── Hằng số ─────────────────────────────────────────────────────────────────

const STORAGE_KEY = "@crash_reporter/queue";
const MAX_QUEUE_SIZE = 50;
const MAX_MESSAGE_LENGTH = 2000;
const MAX_STACK_LENGTH = 20000;

const API_URL =
  typeof process !== "undefined"
    ? (process.env.EXPO_PUBLIC_API_URL ?? "")
    : "";
const CRASH_LOGS_ENDPOINT = `${API_URL}/api/v1/crash-logs`;

// ─── Kiểu nội bộ ─────────────────────────────────────────────────────────────

/** CrashPayload + khóa dedup nội bộ (_dk). Trường _dk bị bỏ trước khi gửi server. */
type StoredItem = CrashPayload & { _dk: string };

// ─── I/O AsyncStorage ─────────────────────────────────────────────────────────

/** Đọc hàng đợi từ AsyncStorage. Ném lỗi nếu I/O thất bại (bọc ở caller). */
async function readQueue(): Promise<StoredItem[]> {
  const raw = await AsyncStorage.getItem(STORAGE_KEY);
  if (!raw) return [];
  return JSON.parse(raw) as StoredItem[];
}

/** Ghi hàng đợi vào AsyncStorage. Ném lỗi nếu I/O thất bại (bọc ở caller). */
async function writeQueue(items: StoredItem[]): Promise<void> {
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

// ─── API công khai ────────────────────────────────────────────────────────────

/**
 * Thêm crash vào hàng đợi AsyncStorage.
 *
 * Dedup: bỏ qua bản ghi mới nếu cặp (fingerprint_được_cung_cấp, hash_nội_dung) đã tồn tại.
 * Điều này đảm bảo:
 *   - Cùng fingerprint + cùng nội dung → bỏ qua (tránh spam cùng lỗi).
 *   - Cùng fingerprint + nội dung khác → cho phép (lỗi khác nhau, chỉ trùng tag).
 *   - Khác fingerprint + cùng nội dung → cho phép (phân loại khác nhau).
 *
 * Cắt message ≤ 2000 ký tự, stack ≤ 20000 ký tự.
 * FIFO: bỏ bản ghi cũ nhất khi vượt 50.
 *
 * ADR-004: không bao giờ ném lỗi.
 */
export async function report(payload: CrashPayload): Promise<void> {
  try {
    // Cắt payload trước khi lưu
    const truncated: CrashPayload = {
      ...payload,
      message: payload.message.slice(0, MAX_MESSAGE_LENGTH),
      stack: payload.stack ? payload.stack.slice(0, MAX_STACK_LENGTH) : undefined,
    };

    // Tính khóa dedup: kết hợp fingerprint được caller cung cấp + hash từ nội dung thực.
    // Cả hai phải khớp mới bị bỏ — tránh dedup nhầm khi fingerprint giống nhau
    // nhưng nội dung khác (hoặc ngược lại).
    const contentHash = computeFingerprint(
      payload.source,
      payload.message,
      payload.stack,
    );
    const dedupKey = `${payload.fingerprint}::${contentHash}`;

    const current = await readQueue();

    // Bỏ qua nếu đã có bản ghi với cùng khóa dedup
    if (current.some((item) => item._dk === dedupKey)) {
      return;
    }

    // Tạo item có khóa dedup
    const stored: StoredItem = { ...truncated, _dk: dedupKey };

    // FIFO: thêm mới vào cuối, bỏ cũ nhất từ đầu nếu vượt giới hạn
    const updated = [...current, stored];
    if (updated.length > MAX_QUEUE_SIZE) {
      updated.splice(0, updated.length - MAX_QUEUE_SIZE);
    }

    await writeQueue(updated);
  } catch {
    // ADR-004: nuốt lỗi (AsyncStorage không khả dụng, JSON hỏng, v.v.)
  }
}

/**
 * Gửi toàn bộ hàng đợi lên server theo batch.
 * Xóa hàng đợi chỉ khi server xác nhận thành công (response.ok).
 * Gọi qua global.fetch trực tiếp để tránh đệ quy khi apiFetch gây crash mới.
 *
 * ADR-004: không bao giờ ném lỗi.
 */
export async function flush(accessToken: string): Promise<void> {
  try {
    const queue = await readQueue();
    if (queue.length === 0) return; // không gọi fetch khi hàng đợi rỗng

    // Bỏ trường nội bộ _dk trước khi gửi lên server
    const items = queue.map(({ _dk: _ignored, ...item }: StoredItem) => item);

    const response = await (global.fetch as unknown as typeof fetch)(CRASH_LOGS_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({ items }),
    });

    if (response.ok) {
      // Xóa hàng đợi chỉ khi server xác nhận — giữ nguyên nếu lỗi để retry sau
      try {
        await AsyncStorage.removeItem(STORAGE_KEY);
      } catch {
        // Nuốt lỗi removeItem — hàng đợi vẫn sẽ được flush lại lần sau
      }
    }
  } catch {
    // ADR-004: nuốt lỗi (network thất bại, fetch ném, v.v.)
  }
}

/**
 * Đọc hàng đợi hiện tại.
 * Dùng để kiểm tra trạng thái hoặc trong test.
 * Trả về mảng rỗng nếu lỗi.
 */
export async function getQueue(): Promise<CrashPayload[]> {
  try {
    return await readQueue();
  } catch {
    return [];
  }
}

/**
 * Xóa toàn bộ hàng đợi.
 * Dùng khi đăng xuất hoặc reset trong test.
 * ADR-004: không ném lỗi.
 */
export async function clearQueue(): Promise<void> {
  try {
    await AsyncStorage.removeItem(STORAGE_KEY);
  } catch {
    // ADR-004: nuốt lỗi
  }
}
