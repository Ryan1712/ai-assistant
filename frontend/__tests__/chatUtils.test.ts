/**
 * Test chatUtils — hàm thuần chuyển Message[] → Row[].
 *
 * Bao gồm 2 nhóm test:
 *  1. messagesToRows: chuyển message thành rows đúng loại, không còn cross-conv divider.
 *  2. labelForTool: trả nhãn tiếng Việt hoặc fallback.
 *
 * Không cần navigation/API mock vì đây là hàm thuần.
 */
import { messagesToRows, labelForTool, textOfMessage } from "../app/main/chatUtils";
import type { Message } from "../src/api/chat";

// Helper tạo Message tối giản
function makeMsg(
  overrides: Partial<Message> & { role: Message["role"]; textContent?: string },
): Message {
  return {
    id: overrides.id ?? "m1",
    conversation_id: overrides.conversation_id ?? "conv-1",
    chat_request_id: overrides.chat_request_id ?? null,
    role: overrides.role,
    content: overrides.content ?? (overrides.textContent != null
      ? [{ type: "text" as const, text: overrides.textContent }]
      : []),
    voice_note_id: overrides.voice_note_id ?? null,
    is_seed: overrides.is_seed ?? false,
    created_at: overrides.created_at ?? "2026-08-08T00:00:00Z",
  };
}

// ─── textOfMessage ────────────────────────────────────────────────────────────

describe("textOfMessage", () => {
  it("trả rỗng khi content không có text block", () => {
    const m = makeMsg({ role: "assistant", content: [] });
    expect(textOfMessage(m)).toBe("");
  });

  it("ghép các text block thành 1 chuỗi", () => {
    const m = makeMsg({
      role: "assistant",
      content: [
        { type: "text", text: "Xin chào" },
        { type: "text", text: "Bạn khỏe không?" },
      ],
    });
    expect(textOfMessage(m)).toBe("Xin chào\nBạn khỏe không?");
  });

  it("bỏ qua block không phải text", () => {
    const m = makeMsg({
      role: "assistant",
      content: [
        { type: "text", text: "OK" },
        { type: "tool_use", id: "t1", name: "create_task", input: {} },
      ],
    });
    expect(textOfMessage(m)).toBe("OK");
  });
});

// ─── labelForTool ─────────────────────────────────────────────────────────────

describe("labelForTool", () => {
  it("trả nhãn tiếng Việt cho tool đã biết", () => {
    expect(labelForTool("create_task")).toBe("Tạo task");
    expect(labelForTool("list_projects")).toBe("Tra cứu project");
    expect(labelForTool("use_skill")).toBe("Dùng skill");
  });

  it("fallback: thay _ bằng space cho tool không có trong bảng", () => {
    expect(labelForTool("unknown_tool_xyz")).toBe("unknown tool xyz");
  });
});

// ─── messagesToRows ───────────────────────────────────────────────────────────

describe("messagesToRows", () => {
  it("danh sách rỗng → rows rỗng", () => {
    expect(messagesToRows([])).toEqual([]);
  });

  it("message user → row kind user", () => {
    const msgs = [makeMsg({ id: "u1", role: "user", textContent: "Xin chào" })];
    const rows = messagesToRows(msgs);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ key: "u1", kind: "user", text: "Xin chào" });
  });

  it("message assistant → row kind assistant", () => {
    const msgs = [makeMsg({ id: "a1", role: "assistant", textContent: "Chào bạn" })];
    const rows = messagesToRows(msgs);
    expect(rows[0]).toMatchObject({ key: "a1", kind: "assistant", text: "Chào bạn" });
  });

  it("message is_seed truyền sang row", () => {
    const msgs = [makeMsg({ id: "s1", role: "assistant", textContent: "Seed", is_seed: true })];
    const rows = messagesToRows(msgs);
    expect(rows[0]).toMatchObject({ isSeed: true });
  });

  it("voice_note_id truyền sang row", () => {
    const msgs = [
      makeMsg({ id: "v1", role: "user", textContent: "Ghi âm", voice_note_id: "vn-abc" }),
    ];
    const rows = messagesToRows(msgs);
    expect(rows[0]).toMatchObject({ voiceNoteId: "vn-abc" });
  });

  it("message không có text nhưng có tool_use → chỉ sinh system row", () => {
    const msgs = [
      makeMsg({
        id: "t1",
        role: "assistant",
        content: [{ type: "tool_use", id: "tu1", name: "create_task", input: {} }],
      }),
    ];
    const rows = messagesToRows(msgs);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ kind: "system", text: "Tạo task" });
  });

  it("message có cả text lẫn tool_use → 2 rows (assistant + system)", () => {
    const msgs = [
      makeMsg({
        id: "m1",
        role: "assistant",
        content: [
          { type: "text", text: "Đang tạo task..." },
          { type: "tool_use", id: "tu1", name: "create_task", input: {} },
        ],
      }),
    ];
    const rows = messagesToRows(msgs);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ kind: "assistant", text: "Đang tạo task..." });
    expect(rows[1]).toMatchObject({ kind: "system", text: "Tạo task" });
  });

  it("suggest_replies tool_use → row kind choices", () => {
    const msgs = [
      makeMsg({
        id: "m2",
        role: "assistant",
        content: [
          {
            type: "tool_use",
            id: "tu2",
            name: "suggest_replies",
            input: { options: ["Có", "Không", "Chưa biết"] },
          },
        ],
      }),
    ];
    const rows = messagesToRows(msgs);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ kind: "choices", options: ["Có", "Không", "Chưa biết"] });
  });

  it("suggest_replies không có options → không sinh row choices", () => {
    const msgs = [
      makeMsg({
        id: "m3",
        role: "assistant",
        content: [
          { type: "tool_use", id: "tu3", name: "suggest_replies", input: { options: [] } },
        ],
      }),
    ];
    const rows = messagesToRows(msgs);
    expect(rows).toHaveLength(0);
  });

  it("KHÔNG sinh divider khi messages từ cùng 1 conversation (single-conv model)", () => {
    // Mô hình mới: dù conversation_id giống hay khác, không bao giờ sinh divider
    const msgs = [
      makeMsg({ id: "m1", role: "user", textContent: "Câu hỏi 1", conversation_id: "conv-A" }),
      makeMsg({ id: "m2", role: "assistant", textContent: "Trả lời 1", conversation_id: "conv-A" }),
    ];
    const rows = messagesToRows(msgs);
    // Không có row nào kind "system" chứa "cuộc trò chuyện mới"
    const dividers = rows.filter(
      (r) => r.kind === "system" && r.text.includes("cuộc trò chuyện mới"),
    );
    expect(dividers).toHaveLength(0);
    expect(rows).toHaveLength(2);
  });

  it("nhiều messages → rows đúng thứ tự", () => {
    const msgs = [
      makeMsg({ id: "m1", role: "user", textContent: "Q1" }),
      makeMsg({ id: "m2", role: "assistant", textContent: "A1" }),
      makeMsg({ id: "m3", role: "user", textContent: "Q2" }),
    ];
    const rows = messagesToRows(msgs);
    expect(rows).toHaveLength(3);
    expect(rows.map((r) => r.kind)).toEqual(["user", "assistant", "user"]);
    expect(rows.map((r) => (r as any).text)).toEqual(["Q1", "A1", "Q2"]);
  });

  it("mở conv theo id cụ thể → chỉ hiện message của conv đó (không bị pha từ conv khác)", () => {
    // Trong mô hình mới, caller chỉ truyền messages của 1 conv vào messagesToRows.
    // Test này xác nhận rằng nếu messages đến từ 1 conv, rows phản ánh đúng conv đó.
    const msgs = [
      makeMsg({ id: "c1-m1", role: "user", textContent: "Hỏi conv C1", conversation_id: "conv-C1" }),
      makeMsg({ id: "c1-m2", role: "assistant", textContent: "Trả lời C1", conversation_id: "conv-C1" }),
    ];
    const rows = messagesToRows(msgs);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ key: "c1-m1", text: "Hỏi conv C1" });
    expect(rows[1]).toMatchObject({ key: "c1-m2", text: "Trả lời C1" });
  });
});
