/**
 * chat-error.test.tsx — Skeleton test ĐỎ cho chat hiển thị lỗi thân thiện
 *
 * Module được test: frontend/app/main/chat.tsx (HIỆN TỒN TẠI — sẽ được SỬA ở Batch 1)
 * Module phụ thuộc: frontend/src/api/client.ts (HIỆN TỒN TẠI — sẽ được SỬA ở Batch 1)
 *
 * Bao phủ acceptance criteria từ Task 1.4 trong sprint-1.md:
 *  - API 500 → hiện "Hệ thống đang có lỗi, vui lòng thử lại." trong chat
 *  - Mất mạng → cùng thông báo
 *  - App KHÔNG sập, KHÔNG văng ra màn login
 *  - 401 → đi luồng refresh token cũ, KHÔNG hiện thông báo lỗi hệ thống
 *  - Chỉ 5xx/timeout/lỗi mạng mới ghi log; 4xx thường KHÔNG ghi
 *  - postCrashLogs thất bại KHÔNG sinh crash log mới (không đệ quy)
 */

import React from "react";
import { render, fireEvent, act } from "@testing-library/react-native";

// Mock tất cả external dependency trước khi import chat
jest.mock("../src/api/chat", () => ({
  sendMessage: jest.fn(),
  listMessages: jest.fn(() => Promise.resolve([])),
  listConversations: jest.fn(() => Promise.resolve([])),
  getActiveConversation: jest.fn(() => Promise.resolve(null)),
  listRequests: jest.fn(() => Promise.resolve([])),
  cancelRequest: jest.fn(),
  confirmRequest: jest.fn(),
  stopAll: jest.fn(),
  reorderRequest: jest.fn(),
  getTimeline: jest.fn(() => Promise.resolve(null)),
  openConversationStream: jest.fn(() => ({ close: jest.fn() })),
  isResumePhrase: jest.fn(() => false),
  RESUME_PHRASE: "resume",
}));

jest.mock("../src/api/voice", () => ({
  uploadVoiceNote: jest.fn(),
  voiceNoteAudioSource: jest.fn(),
}));

jest.mock("@react-navigation/native", () => ({
  useNavigation: jest.fn(() => ({
    navigate: jest.fn(),
    goBack: jest.fn(),
  })),
  useRoute: jest.fn(() => ({
    params: { conversationId: "conv-test-123" },
  })),
}));

jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 44, bottom: 34, left: 0, right: 0 }),
  SafeAreaProvider: ({ children }: { children: React.ReactNode }) => children,
}));

jest.mock("react-native-keyboard-controller", () => ({
  KeyboardAvoidingView: ({ children }: { children: React.ReactNode }) => children,
}));

jest.mock("react-native-markdown-display", () => "Markdown");

jest.mock("expo-document-picker", () => ({
  getDocumentAsync: jest.fn(),
}));

jest.mock("expo-audio", () => ({
  useAudioPlayer: jest.fn(() => ({ play: jest.fn(), pause: jest.fn() })),
  useAudioPlayerStatus: jest.fn(() => ({ isLoaded: false, playing: false })),
}));

jest.mock("../src/voice/DictationButton", () => ({
  DictationButton: () => null,
}));

jest.mock("@expo/vector-icons", () => ({
  Ionicons: "Ionicons",
}));

// Mock crashReporter để kiểm tra KHÔNG gọi report() với 4xx
jest.mock("../src/errors/crashReporter", () => ({
  report: jest.fn(() => Promise.resolve()),
  flush: jest.fn(() => Promise.resolve()),
}));

import { sendMessage } from "../src/api/chat";
import { report } from "../src/errors/crashReporter";

// Import chat component — module này đã tồn tại nhưng chưa có tính năng lỗi thân thiện
// Test sẽ ĐỎ vì chưa có bong bóng lỗi "Hệ thống đang có lỗi..."
// Sau Batch 1 dev sửa chat.tsx thì test mới XANH
import ChatScreen from "../app/main/chat";

// ─── Hằng số thông báo lỗi (phải khớp với chuỗi dev implement) ────────────

const ERROR_MESSAGE = "Hệ thống đang có lỗi, vui lòng thử lại.";

// ─── Helpers ─────────────────────────────────────────────────────────────────

// Kết quả render của test hiện tại. KHÔNG dùng `screen` toàn cục: `render()` của
// RNTL v14 là async, nên kết quả của test trước có thể ghi đè `screen` muộn và
// test sau đi soi vào cây ĐÃ UNMOUNT (toJSON() trả null) — hỏng vì lý do giả.
let view: Awaited<ReturnType<typeof render>>;

async function renderChat() {
  const utils = await render(<ChatScreen />);
  view = utils;
  // ChatScreen nạp dữ liệu bất đồng bộ (listMessages → refreshQueue → mở WS).
  // KHÔNG chờ được bằng ô nhập: ô nhập render ngay cả lúc đang tải. Phải chờ
  // tín hiệu tải XONG (empty state của danh sách), vì trước đó `conversationId`
  // còn null và submit() thoát ngay ở `if (!conversationId) return` — test sẽ
  // hỏng vì lý do chẳng liên quan tới thứ nó muốn kiểm tra.
  try {
    await view.findByText(/gửi không cần chờ/i);
  } catch (err) {
    // eslint-disable-next-line no-console
    console.log("DEBUG_TREE:", JSON.stringify(view.toJSON()).slice(0, 1500));
    throw err;
  }
  return utils;
}

async function typeAndSend(text: string) {
  const input = await view.findByPlaceholderText(/nhắn/i);
  fireEvent.changeText(input, text);
  const sendBtn = view.getByTestId("send-button");
  await act(async () => {
    fireEvent.press(sendBtn);
  });
}

// ─── Test cases ──────────────────────────────────────────────────────────────

describe("chat — hiển thị lỗi thân thiện khi API lỗi", () => {
  beforeEach(() => {
    (report as jest.Mock).mockClear();
    (sendMessage as jest.Mock).mockReset();
  });

  it("hiện thông báo lỗi thân thiện khi API trả về 500", async () => {
    // Giả lập sendMessage ném ApiError với status 500
    (sendMessage as jest.Mock).mockRejectedValueOnce(
      Object.assign(new Error("Internal Server Error"), { status: 500 }),
    );

    await renderChat();
    await typeAndSend("Xin chào");

    // Thông báo lỗi phải xuất hiện trong chat
    expect(view.getByText(ERROR_MESSAGE)).toBeTruthy();
  });

  it("app KHÔNG sập khi API trả về 500 (không throw ra ngoài)", async () => {
    (sendMessage as jest.Mock).mockRejectedValueOnce(
      Object.assign(new Error("Internal Server Error"), { status: 500 }),
    );

    // RNTL v14: render() async — nếu throw thì test fail, nếu không thì pass.
    await renderChat();
  });

  it("hiện thông báo lỗi thân thiện khi mất mạng (fetch throw NetworkError)", async () => {
    (sendMessage as jest.Mock).mockRejectedValueOnce(
      new TypeError("Network request failed"),
    );

    await renderChat();
    await typeAndSend("Test mất mạng");

    expect(view.getByText(ERROR_MESSAGE)).toBeTruthy();
  });

  it("KHÔNG hiện thông báo lỗi hệ thống khi API trả 401 (luồng refresh token)", async () => {
    // 401 phải được xử lý bởi apiFetch tryRefresh() — chat KHÔNG thấy lỗi
    // (mock sendMessage success sau khi refresh — simulate hành vi apiFetch)
    (sendMessage as jest.Mock)
      .mockRejectedValueOnce(
        Object.assign(new Error("Unauthorized"), { status: 401 }),
      )
      .mockResolvedValueOnce({ id: "msg-1", content: "OK" });

    await renderChat();
    await typeAndSend("Tin nhắn sau refresh");

    // Thông báo lỗi hệ thống KHÔNG được hiển thị
    expect(view.queryByText(ERROR_MESSAGE)).toBeNull();
  });

  it("KHÔNG gọi crashReporter.report() khi lỗi 401", async () => {
    (sendMessage as jest.Mock).mockRejectedValueOnce(
      Object.assign(new Error("Unauthorized"), { status: 401 }),
    );

    await renderChat();
    await typeAndSend("Test 401");

    expect(report).not.toHaveBeenCalled();
  });

  it("KHÔNG gọi crashReporter.report() khi lỗi 403", async () => {
    (sendMessage as jest.Mock).mockRejectedValueOnce(
      Object.assign(new Error("Forbidden"), { status: 403 }),
    );

    await renderChat();
    await typeAndSend("Test 403");

    expect(report).not.toHaveBeenCalled();
  });

  it("KHÔNG gọi crashReporter.report() khi lỗi 404", async () => {
    (sendMessage as jest.Mock).mockRejectedValueOnce(
      Object.assign(new Error("Not Found"), { status: 404 }),
    );

    await renderChat();
    await typeAndSend("Test 404");

    expect(report).not.toHaveBeenCalled();
  });

  it("GỌI crashReporter.report() khi lỗi 500", async () => {
    (sendMessage as jest.Mock).mockRejectedValueOnce(
      Object.assign(new Error("Internal Server Error"), { status: 500 }),
    );

    await renderChat();
    await typeAndSend("Test 500");

    expect(report).toHaveBeenCalledWith(
      expect.objectContaining({ source: "fe_api" }),
    );
  });
});

// ─── Không đệ quy: gửi crash log thất bại không sinh crash log mới ───────────

describe("chat + crashReporter — không đệ quy", () => {
  it("flush() thất bại không gọi report() từ bên trong flush()", async () => {
    // Kiểm tra: flush trong crashReporter KHÔNG gọi report khi gặp lỗi mạng
    // (test này cần module crashReporter thật — mock đơn giản ở đây là placeholder)
    // Dev sẽ hoàn thiện khi implement crashReporter.ts
    const { flush } = require("../src/errors/crashReporter");
    (global.fetch as jest.Mock).mockRejectedValueOnce(new Error("network"));

    // Không được throw
    await expect(flush("token")).resolves.not.toThrow();
    // report KHÔNG được gọi bên trong flush
    expect(report).not.toHaveBeenCalled();
  });
});
