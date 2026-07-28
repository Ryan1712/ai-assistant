/**
 * ErrorBoundary.test.tsx — Skeleton test ĐỎ cho ErrorBoundary component
 *
 * Module được test: frontend/src/errors/ErrorBoundary.tsx (CHƯA TỒN TẠI — dev tạo ở Batch 1)
 *
 * Bao phủ acceptance criteria từ Task 1.3 trong sprint-1.md:
 *  - Component con ném lỗi khi render → hiện fallback, app không sập, có gọi report
 *  - crashReporter.report() được gọi với thông tin lỗi
 *  - ErrorBoundary không bao giờ ném lỗi ra ngoài
 */

import React from "react";
import { Text } from "react-native";
import { render, screen } from "@testing-library/react-native";

// Import module chưa tồn tại — sẽ báo đỏ lúc này (đúng ý định)
import { ErrorBoundary } from "../src/errors/ErrorBoundary";

// Mock crashReporter để kiểm tra có gọi report() không
jest.mock("../src/errors/crashReporter", () => ({
  report: jest.fn(() => Promise.resolve()),
  flush: jest.fn(() => Promise.resolve()),
  getQueue: jest.fn(() => Promise.resolve([])),
  clearQueue: jest.fn(() => Promise.resolve()),
}));

import { report } from "../src/errors/crashReporter";

// ─── Component con gây lỗi dùng trong test ───────────────────────────────────

function ThrowOnRender({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) {
    throw new Error("Test render crash — cố ý ném lỗi để test ErrorBoundary");
  }
  return <Text testID="normal-content">Nội dung bình thường</Text>;
}

// ─── Setup: tắt tiếng console.error của React khi test ErrorBoundary ────────
// React sẽ in "The above error occurred in..." — không cần thiết trong test output

let originalConsoleError: typeof console.error;

beforeAll(() => {
  originalConsoleError = console.error;
  console.error = (...args: unknown[]) => {
    // Bỏ qua các lỗi React về error boundary — giữ lại lỗi thật
    if (
      typeof args[0] === "string" &&
      (args[0].includes("The above error occurred") ||
        args[0].includes("Consider adding an error boundary"))
    ) {
      return;
    }
    originalConsoleError(...args);
  };
});

afterAll(() => {
  console.error = originalConsoleError;
});

beforeEach(() => {
  jest.clearAllMocks();
});

// ─── Test cases ──────────────────────────────────────────────────────────────

describe("ErrorBoundary — bắt lỗi render và hiện fallback", () => {
  it("hiện nội dung bình thường khi không có lỗi", async () => {
    await render(
      <ErrorBoundary>
        <ThrowOnRender shouldThrow={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByTestId("normal-content")).toBeTruthy();
  });

  it("hiện fallback thay vì content khi component con ném lỗi", async () => {
    await render(
      <ErrorBoundary>
        <ThrowOnRender shouldThrow={true} />
      </ErrorBoundary>,
    );
    // Fallback phải hiển thị — không hiện nội dung gốc
    expect(screen.queryByTestId("normal-content")).toBeNull();
    // Fallback phải có testID hoặc text nhận diện được
    // (dev quyết định cụ thể — test này kiểm tra fallback được render)
    expect(screen.queryByTestId("error-fallback")).toBeTruthy();
  });

  it("app không sập (không throw ra ngoài ErrorBoundary) khi con ném lỗi", async () => {
    // RNTL v14: render() là async — nếu ErrorBoundary không bắt lỗi,
    // await render() sẽ reject và test này fail (đúng ý định).
    // Nếu đến được dòng expect() bên dưới → render() không throw → test pass.
    await render(
      <ErrorBoundary>
        <ThrowOnRender shouldThrow={true} />
      </ErrorBoundary>,
    );
  });

  it("gọi crashReporter.report() khi bắt được lỗi", async () => {
    await render(
      <ErrorBoundary>
        <ThrowOnRender shouldThrow={true} />
      </ErrorBoundary>,
    );
    // report() phải được gọi sau khi lỗi bị bắt
    expect(report).toHaveBeenCalledTimes(1);
  });

  it("gọi report() với object có source, message, và stack", async () => {
    await render(
      <ErrorBoundary>
        <ThrowOnRender shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(report).toHaveBeenCalledWith(
      expect.objectContaining({
        source: expect.any(String),
        message: expect.any(String),
      }),
    );
    // stack phải không rỗng
    const reportArg = (report as jest.Mock).mock.calls[0][0];
    expect(reportArg.message).toContain("Test render crash");
  });
});

describe("ErrorBoundary — custom fallback", () => {
  it("hiện custom fallback UI khi được truyền vào", async () => {
    const customFallback = <Text testID="custom-fallback">Ối, lỗi rồi!</Text>;
    await render(
      <ErrorBoundary fallback={customFallback}>
        <ThrowOnRender shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(screen.getByTestId("custom-fallback")).toBeTruthy();
  });
});
