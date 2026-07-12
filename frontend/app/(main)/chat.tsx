import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import {
  ChatRequest,
  Message,
  cancelRequest,
  confirmRequest,
  createConversation,
  listConversations,
  listMessages,
  listRequests,
  sendMessage,
  stopAll,
} from "../../src/api/chat";
import { WsEvent, openConversationStream } from "../../src/api/ws";

type Row =
  | { key: string; kind: "user" | "assistant"; text: string }
  | { key: string; kind: "streaming"; text: string }
  | { key: string; kind: "system"; text: string };

function textOfMessage(m: Message): string {
  return m.content
    .map((b) => (b.type === "text" ? b.text : ""))
    .filter(Boolean)
    .join("\n");
}

export default function Chat() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [queue, setQueue] = useState<ChatRequest[]>([]);
  const [input, setInput] = useState("");
  const [pendingConfirm, setPendingConfirm] = useState<{
    requestId: string;
    toolName: string;
  } | null>(null);
  const streamingText = useRef<Map<string, string>>(new Map());
  const listRef = useRef<FlatList>(null);
  const closeWs = useRef<(() => void) | null>(null);

  const refreshQueue = useCallback(async (cid: string) => {
    const reqs = await listRequests(cid);
    setQueue(reqs.filter((r) => r.status === "queued" || r.status === "running"));
    const waiting = reqs.find((r) => r.status === "awaiting_confirmation");
    if (waiting) setPendingConfirm({ requestId: waiting.id, toolName: "hành động nhạy cảm" });
  }, []);

  const loadHistory = useCallback(async (cid: string) => {
    const msgs = await listMessages(cid);
    setRows(
      msgs
        .map((m): Row | null => {
          const text = textOfMessage(m);
          if (!text) return null;
          return { key: m.id, kind: m.role === "user" ? "user" : "assistant", text };
        })
        .filter((r): r is Row => r !== null),
    );
  }, []);

  const onWsEvent = useCallback(
    (cid: string) => (e: WsEvent) => {
      if (e.type === "token") {
        const cur = (streamingText.current.get(e.chat_request_id) ?? "") + e.text;
        streamingText.current.set(e.chat_request_id, cur);
        setRows((prev) => {
          const key = `stream-${e.chat_request_id}`;
          const idx = prev.findIndex((r) => r.key === key);
          const row: Row = { key, kind: "streaming", text: cur };
          if (idx === -1) return [...prev, row];
          const next = [...prev];
          next[idx] = row;
          return next;
        });
      } else if (e.type === "request_done") {
        streamingText.current.delete(e.chat_request_id);
        setRows((prev) =>
          prev.map((r) =>
            r.key === `stream-${e.chat_request_id}` ? { ...r, kind: "assistant" } : r,
          ),
        );
        refreshQueue(cid);
      } else if (e.type === "request_failed") {
        setRows((prev) => [
          ...prev,
          { key: `fail-${e.chat_request_id}`, kind: "system", text: `⚠️ Yêu cầu lỗi: ${e.error} — các yêu cầu sau vẫn chạy tiếp.` },
        ]);
        refreshQueue(cid);
      } else if (e.type === "confirmation_required") {
        setPendingConfirm({ requestId: e.chat_request_id, toolName: e.tool_name });
        refreshQueue(cid);
      } else if (e.type === "status_update") {
        refreshQueue(cid);
      }
    },
    [refreshQueue],
  );

  useEffect(() => {
    (async () => {
      const convs = await listConversations();
      const conv = convs[0] ?? (await createConversation("Cuộc trò chuyện đầu tiên"));
      setConversationId(conv.id);
      await loadHistory(conv.id);
      await refreshQueue(conv.id);
      closeWs.current = await openConversationStream(conv.id, onWsEvent(conv.id));
    })();
    return () => closeWs.current?.();
  }, [loadHistory, onWsEvent, refreshQueue]);

  const submit = async () => {
    if (!conversationId || !input.trim()) return;
    const content = input.trim();
    setInput("");
    const req = await sendMessage(conversationId, content);
    setRows((prev) => [...prev, { key: `u-${req.id}`, kind: "user", text: content }]);
    await refreshQueue(conversationId);
  };

  const resolveConfirm = async (approved: boolean) => {
    if (!pendingConfirm || !conversationId) return;
    await confirmRequest(pendingConfirm.requestId, approved);
    setPendingConfirm(null);
    await refreshQueue(conversationId);
  };

  const running = queue.find((q) => q.status === "running");

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: "#f9fafb" }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      {queue.length > 0 && (
        <View style={styles.queueBar}>
          <Text style={{ flex: 1 }}>
            Đang xử lý {running ? 1 : 0}/{queue.length}
            {running ? ` — “${running.content.slice(0, 40)}”` : ""}
          </Text>
          <TouchableOpacity onPress={() => conversationId && stopAll(conversationId)}>
            <Text style={{ color: "#dc2626", fontWeight: "600" }}>Dừng tất cả</Text>
          </TouchableOpacity>
        </View>
      )}
      <FlatList
        ref={listRef}
        data={rows}
        keyExtractor={(r) => r.key}
        contentContainerStyle={{ padding: 12, gap: 8 }}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
        renderItem={({ item }) => (
          <View
            style={[
              styles.bubble,
              item.kind === "user"
                ? styles.userBubble
                : item.kind === "system"
                  ? styles.systemBubble
                  : styles.aiBubble,
            ]}
          >
            <Text style={item.kind === "user" ? { color: "#fff" } : undefined}>
              {item.text}
              {item.kind === "streaming" ? " ▍" : ""}
            </Text>
          </View>
        )}
      />
      {pendingConfirm && (
        <View style={styles.confirmBar}>
          <Text style={{ marginBottom: 8 }}>
            AI muốn thực hiện hành động nhạy cảm: {pendingConfirm.toolName}. Xác nhận?
          </Text>
          <View style={{ flexDirection: "row", gap: 12 }}>
            <TouchableOpacity style={styles.okBtn} onPress={() => resolveConfirm(true)}>
              <Text style={{ color: "#fff" }}>Đồng ý</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.denyBtn} onPress={() => resolveConfirm(false)}>
              <Text style={{ color: "#fff" }}>Từ chối</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}
      <View style={styles.inputBar}>
        <TextInput
          style={styles.input}
          placeholder="Nhắn cho trợ lý AI… (gửi không cần chờ)"
          value={input}
          onChangeText={setInput}
          onSubmitEditing={submit}
          multiline
        />
        <TouchableOpacity style={styles.sendBtn} onPress={submit}>
          <Text style={{ color: "#fff", fontWeight: "700" }}>Gửi</Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  queueBar: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#fef3c7",
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  bubble: { borderRadius: 12, padding: 10, maxWidth: "85%" },
  userBubble: { backgroundColor: "#2563eb", alignSelf: "flex-end" },
  aiBubble: { backgroundColor: "#e5e7eb", alignSelf: "flex-start" },
  systemBubble: { backgroundColor: "#fee2e2", alignSelf: "center" },
  confirmBar: { backgroundColor: "#fff7ed", padding: 12, borderTopWidth: 1, borderColor: "#fdba74" },
  okBtn: { backgroundColor: "#16a34a", borderRadius: 8, paddingHorizontal: 16, paddingVertical: 8 },
  denyBtn: { backgroundColor: "#dc2626", borderRadius: 8, paddingHorizontal: 16, paddingVertical: 8 },
  inputBar: {
    flexDirection: "row",
    alignItems: "flex-end",
    padding: 10,
    gap: 8,
    borderTopWidth: 1,
    borderColor: "#e5e7eb",
    backgroundColor: "#fff",
  },
  input: {
    flex: 1,
    borderWidth: 1,
    borderColor: "#d1d5db",
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
    maxHeight: 120,
    fontSize: 16,
  },
  sendBtn: {
    backgroundColor: "#2563eb",
    borderRadius: 10,
    paddingHorizontal: 18,
    paddingVertical: 10,
  },
});
