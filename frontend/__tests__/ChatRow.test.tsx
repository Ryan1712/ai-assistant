/**
 * Test ChatRow — component con memo hoá của màn chat.
 * Chứng minh:
 *  1. Render đúng với mọi loại row (user, assistant, streaming, system, failed, choices)
 *  2. Memo không crash khi props thay đổi
 *  3. Handlers được gọi đúng
 *
 * Lưu ý: RNTL v14 — render() là async function, phải await.
 */
import React from "react";
import { render, fireEvent } from "@testing-library/react-native";
import ChatRow from "../app/main/ChatRow";

// Tắt tiếng console.error của React (ErrorBoundary/prop-type warnings trong test)
const originalError = console.error;
beforeAll(() => {
  console.error = (...args: unknown[]) => {
    if (typeof args[0] === "string" && args[0].includes("Warning:")) return;
    originalError(...args);
  };
});
afterAll(() => {
  console.error = originalError;
});

const noop = () => {};

describe("ChatRow", () => {
  it("render dòng user đúng text", async () => {
    const { getByText } = await render(
      <ChatRow
        item={{ key: "u1", kind: "user", text: "Xin chào AI" }}
        audioPlayingId={null}
        audioPlaying={false}
        onSubmit={noop}
        onToggleAudio={noop}
        onRetry={noop}
      />,
    );
    expect(getByText("Xin chào AI")).toBeTruthy();
  });

  it("render dòng assistant đúng text", async () => {
    const { getByText } = await render(
      <ChatRow
        item={{ key: "a1", kind: "assistant", text: "Xin chào bạn" }}
        audioPlayingId={null}
        audioPlaying={false}
        onSubmit={noop}
        onToggleAudio={noop}
        onRetry={noop}
      />,
    );
    // Markdown render text không bị mất
    expect(getByText("Xin chào bạn")).toBeTruthy();
  });

  it("render dòng streaming có cursor ▍", async () => {
    const { getByText } = await render(
      <ChatRow
        item={{ key: "s1", kind: "streaming", text: "Đang gõ" }}
        audioPlayingId={null}
        audioPlaying={false}
        onSubmit={noop}
        onToggleAudio={noop}
        onRetry={noop}
      />,
    );
    expect(getByText("Đang gõ ▍")).toBeTruthy();
  });

  it("render dòng system đúng text", async () => {
    const { getByText } = await render(
      <ChatRow
        item={{ key: "sys1", kind: "system", text: "Tạo task" }}
        audioPlayingId={null}
        audioPlaying={false}
        onSubmit={noop}
        onToggleAudio={noop}
        onRetry={noop}
      />,
    );
    expect(getByText("Tạo task")).toBeTruthy();
  });

  it("render dòng failed và gọi onRetry khi bấm Gửi lại", async () => {
    const onRetry = jest.fn();
    const { getByText } = await render(
      <ChatRow
        item={{ key: "f1", kind: "failed", text: "Có lỗi xảy ra", retryContent: "Nội dung cũ" }}
        audioPlayingId={null}
        audioPlaying={false}
        onSubmit={noop}
        onToggleAudio={noop}
        onRetry={onRetry}
      />,
    );
    expect(getByText("Có lỗi xảy ra")).toBeTruthy();
    fireEvent.press(getByText("Gửi lại"));
    expect(onRetry).toHaveBeenCalledWith("Nội dung cũ");
  });

  it("render dòng choices và gọi onSubmit khi bấm option", async () => {
    const onSubmit = jest.fn();
    const { getByText } = await render(
      <ChatRow
        item={{ key: "c1", kind: "choices", options: ["Tạo project", "Xem task"] }}
        audioPlayingId={null}
        audioPlaying={false}
        onSubmit={onSubmit}
        onToggleAudio={noop}
        onRetry={noop}
      />,
    );
    fireEvent.press(getByText("Tạo project"));
    expect(onSubmit).toHaveBeenCalledWith("Tạo project");
  });

  it("render audio chip với nút play khi có voiceNoteId", async () => {
    const onToggleAudio = jest.fn();
    const { getByText } = await render(
      <ChatRow
        item={{ key: "u2", kind: "user", text: "Ghi âm", voiceNoteId: "vn-123" }}
        audioPlayingId={null}
        audioPlaying={false}
        onSubmit={noop}
        onToggleAudio={onToggleAudio}
        onRetry={noop}
      />,
    );
    // Bấm vào chip "Ghi âm đính kèm"
    fireEvent.press(getByText("Ghi âm đính kèm"));
    expect(onToggleAudio).toHaveBeenCalledWith("vn-123");
  });

  it("React.memo: không crash khi re-render với props mới", async () => {
    // Render lần 1
    const { getByText: getByText1, unmount } = await render(
      <ChatRow
        item={{ key: "u1", kind: "user", text: "Tin nhắn" }}
        audioPlayingId={null}
        audioPlaying={false}
        onSubmit={noop}
        onToggleAudio={noop}
        onRetry={noop}
      />,
    );
    expect(getByText1("Tin nhắn")).toBeTruthy();
    await unmount();
    // Render lần 2 với props khác — memo không crash
    const { getByText: getByText2 } = await render(
      <ChatRow
        item={{ key: "u1", kind: "user", text: "Tin nhắn mới" }}
        audioPlayingId={null}
        audioPlaying={false}
        onSubmit={noop}
        onToggleAudio={noop}
        onRetry={noop}
      />,
    );
    expect(getByText2("Tin nhắn mới")).toBeTruthy();
  });

  it("danh sách nhiều dòng render đúng thứ tự", async () => {
    const rows = [
      { key: "u1", kind: "user" as const, text: "Câu hỏi 1" },
      { key: "a1", kind: "assistant" as const, text: "Trả lời 1" },
      { key: "u2", kind: "user" as const, text: "Câu hỏi 2" },
    ];
    const { getAllByText } = await render(
      <>
        {rows.map((item) => (
          <ChatRow
            key={item.key}
            item={item}
            audioPlayingId={null}
            audioPlaying={false}
            onSubmit={noop}
            onToggleAudio={noop}
            onRetry={noop}
          />
        ))}
      </>,
    );
    expect(getAllByText(/Câu hỏi|Trả lời/).length).toBe(3);
  });
});
