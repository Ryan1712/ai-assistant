/**
 * crashReporter.test.ts — Skeleton test ĐỎ cho hàng đợi crash và flush
 *
 * Module được test: frontend/src/errors/crashReporter.ts (CHƯA TỒN TẠI — dev tạo ở Batch 1)
 *
 * Các test này sẽ ĐỎ vì thiếu code, KHÔNG phải vì cấu hình sai.
 * Dev ở Batch 1: tạo crashReporter.ts theo File Blueprint trong architecture.md
 *    và làm xanh các test này.
 *
 * Bao phủ acceptance criteria từ Task 1.3 trong sprint-1.md:
 *  - Hàng đợi AsyncStorage, tối đa 50 bản ghi (FIFO)
 *  - Dedupe theo fingerprint trong cùng hàng đợi
 *  - Cắt payload: message ≤ 2000 ký tự, stack ≤ 20000 ký tự
 *  - flush() gửi batch lên server sau khi đăng nhập
 *  - KHÔNG BAO GIỜ ném lỗi ra ngoài (ADR-004)
 */

// Import module chưa tồn tại — sẽ báo đỏ lúc này (đúng ý định)
import {
  report,
  flush,
  getQueue,
  clearQueue,
} from "../src/errors/crashReporter";
import type { CrashPayload } from "../src/errors/types";

import AsyncStorage from "@react-native-async-storage/async-storage";

// ─── Helpers ─────────────────────────────────────────────────────────────────

// Kiểu overrides dùng đúng CrashPayload thay vì string rộng, tránh TypeScript
// widen "fe_js" as const thành string khi spread vào object trả về.
function makeCrash(overrides: Partial<CrashPayload> = {}): CrashPayload {
  return {
    source: "fe_js",
    severity: "error",
    message: "Test crash",
    stack: "Error: Test crash\n  at test.ts:1",
    fingerprint: "fp-test-001",
    occurred_at: new Date().toISOString(),
    client_event_id: `evt-${Date.now()}-${Math.random()}`,
    ...overrides,
  };
}

// ─── Hàng đợi ────────────────────────────────────────────────────────────────

describe("crashReporter — hàng đợi", () => {
  beforeEach(async () => {
    // Reset mock AsyncStorage và hàng đợi trước mỗi test
    (AsyncStorage as jest.Mocked<typeof AsyncStorage>).clear();
    await clearQueue();
  });

  it("report() lưu bản ghi vào hàng đợi AsyncStorage", async () => {
    await report(makeCrash({ message: "lỗi đầu tiên" }));
    const queue = await getQueue();
    expect(queue).toHaveLength(1);
    expect(queue[0].message).toBe("lỗi đầu tiên");
  });

  it("report() nhiều lần thêm nhiều bản ghi vào hàng đợi", async () => {
    await report(makeCrash({ client_event_id: "evt-1", message: "lỗi 1" }));
    await report(makeCrash({ client_event_id: "evt-2", message: "lỗi 2" }));
    const queue = await getQueue();
    expect(queue).toHaveLength(2);
  });

  it("hàng đợi tối đa 50 bản ghi — bản ghi cũ nhất bị bỏ khi vượt quá (FIFO)", async () => {
    // Thêm 50 bản ghi vào hàng đợi
    for (let i = 0; i < 50; i++) {
      await report(makeCrash({ client_event_id: `evt-${i}`, message: `lỗi ${i}` }));
    }

    // Thêm bản ghi thứ 51
    await report(makeCrash({ client_event_id: "evt-new", message: "lỗi mới nhất" }));

    const queue = await getQueue();
    // Hàng đợi vẫn chỉ có 50 bản ghi
    expect(queue).toHaveLength(50);
    // Bản ghi mới nhất phải có mặt (cũ nhất bị bỏ)
    const messages = queue.map((item) => item.message);
    expect(messages).toContain("lỗi mới nhất");
    // Bản ghi cũ nhất (index 0) phải bị bỏ
    expect(messages).not.toContain("lỗi 0");
  });
});

// ─── Dedupe theo fingerprint ─────────────────────────────────────────────────

describe("crashReporter — dedupe theo fingerprint trong hàng đợi", () => {
  beforeEach(async () => {
    (AsyncStorage as jest.Mocked<typeof AsyncStorage>).clear();
    await clearQueue();
  });

  it("cùng fingerprint không thêm bản ghi trùng vào hàng đợi", async () => {
    await report(makeCrash({ fingerprint: "fp-abc", client_event_id: "evt-a1" }));
    await report(makeCrash({ fingerprint: "fp-abc", client_event_id: "evt-a2" }));
    const queue = await getQueue();
    // Chỉ có 1 bản ghi — bản ghi trùng fingerprint bị bỏ qua
    expect(queue).toHaveLength(1);
  });

  it("fingerprint khác nhau tạo bản ghi riêng biệt", async () => {
    await report(makeCrash({ fingerprint: "fp-abc", client_event_id: "evt-a" }));
    await report(makeCrash({ fingerprint: "fp-def", client_event_id: "evt-b" }));
    const queue = await getQueue();
    expect(queue).toHaveLength(2);
  });
});

// ─── Cắt payload ─────────────────────────────────────────────────────────────

describe("crashReporter — cắt payload trước khi lưu", () => {
  beforeEach(async () => {
    (AsyncStorage as jest.Mocked<typeof AsyncStorage>).clear();
    await clearQueue();
  });

  it("message vượt 2000 ký tự bị cắt còn 2000 ký tự", async () => {
    const longMessage = "x".repeat(5000);
    await report(makeCrash({ message: longMessage }));
    const queue = await getQueue();
    expect(queue[0].message.length).toBeLessThanOrEqual(2000);
  });

  it("stack vượt 20000 ký tự bị cắt còn 20000 ký tự", async () => {
    const longStack = "Error\n" + "  at fn (file.ts:1)\n".repeat(1500);
    await report(makeCrash({ stack: longStack }));
    const queue = await getQueue();
    expect(queue[0].stack!.length).toBeLessThanOrEqual(20000);
  });
});

// ─── flush() ─────────────────────────────────────────────────────────────────

describe("crashReporter — flush()", () => {
  beforeEach(async () => {
    (AsyncStorage as jest.Mocked<typeof AsyncStorage>).clear();
    await clearQueue();
  });

  it("flush() gọi fetch gửi batch lên server và xóa hàng đợi sau thành công", async () => {
    // Đặt fetch mock trả về thành công
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ accepted: 2, duplicates: 0 }),
    });

    await report(makeCrash({ client_event_id: "evt-1", message: "lỗi 1" }));
    await report(makeCrash({ client_event_id: "evt-2", message: "lỗi 2" }));

    await flush("test-access-token");

    // fetch phải được gọi
    expect(global.fetch).toHaveBeenCalled();
    // Hàng đợi phải rỗng sau flush thành công
    const queue = await getQueue();
    expect(queue).toHaveLength(0);
  });

  it("flush() không xóa hàng đợi khi server trả về lỗi", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: false,
      status: 500,
    });

    await report(makeCrash({ client_event_id: "evt-3", message: "lỗi 3" }));
    await flush("test-access-token");

    // Hàng đợi còn nguyên vì gửi thất bại
    const queue = await getQueue();
    expect(queue).toHaveLength(1);
  });

  it("flush() không làm gì khi hàng đợi rỗng", async () => {
    await flush("test-access-token");
    expect(global.fetch).not.toHaveBeenCalled();
  });
});

// ─── KHÔNG BAO GIỜ ném lỗi (ADR-004) ────────────────────────────────────────

describe("crashReporter — không bao giờ ném lỗi ra ngoài (ADR-004)", () => {
  it("report() không ném lỗi kể cả khi AsyncStorage.getItem ném", async () => {
    (AsyncStorage.getItem as jest.Mock).mockRejectedValueOnce(
      new Error("storage failure"),
    );
    // Không được throw
    await expect(report(makeCrash())).resolves.not.toThrow();
  });

  it("report() không ném lỗi kể cả khi AsyncStorage.setItem ném", async () => {
    (AsyncStorage.setItem as jest.Mock).mockRejectedValueOnce(
      new Error("quota exceeded"),
    );
    await expect(report(makeCrash())).resolves.not.toThrow();
  });

  it("flush() không ném lỗi kể cả khi fetch ném", async () => {
    (global.fetch as jest.Mock).mockRejectedValueOnce(new Error("network failure"));
    await report(makeCrash({ client_event_id: "evt-safe" }));
    // Không được throw
    await expect(flush("test-token")).resolves.not.toThrow();
  });

  it("flush() không ném lỗi kể cả khi AsyncStorage.removeItem ném", async () => {
    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ accepted: 1, duplicates: 0 }),
    });
    (AsyncStorage.removeItem as jest.Mock).mockRejectedValueOnce(
      new Error("remove failed"),
    );
    await report(makeCrash({ client_event_id: "evt-safe-2" }));
    await expect(flush("test-token")).resolves.not.toThrow();
  });
});
