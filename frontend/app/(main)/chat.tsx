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
  reorderRequest,
  sendMessage,
  stopAll,
} from "../../src/api/chat";
import { WsEvent, openConversationStream } from "../../src/api/ws";
import { colors, radius, spacing, type } from "../../src/ui/theme";

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

  const cancelQueued = async (requestId: string) => {
    if (!conversationId) return;
    try {
      await cancelRequest(requestId);
    } catch {}
    await refreshQueue(conversationId);
  };

  const prioritize = async (requestId: string) => {
    if (!conversationId) return;
    try {
      await reorderRequest(requestId, null); // before_id null = lên đầu hàng đợi
    } catch {}
    await refreshQueue(conversationId);
  };

  const running = queue.find((q) => q.status === "running");
  const queuedOnly = queue.filter((q) => q.status === "queued");

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.bg }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      {queue.length > 0 && (
        <View style={styles.queueBar}>
          <Text style={{ flex: 1, color: colors.text }}>
            Đang xử lý {running ? 1 : 0}/{queue.length}
            {running ? ` — “${running.content.slice(0, 40)}”` : ""}
          </Text>
          <TouchableOpacity onPress={() => conversationId && stopAll(conversationId)}>
            <Text style={{ color: colors.danger, fontWeight: "700" }}>Dừng tất cả</Text>
          </TouchableOpacity>
        </View>
      )}
      {queuedOnly.length > 0 && (
        <View style={styles.queueList}>
          <Text style={styles.queueTitle}>Hàng đợi ({queuedOnly.length})</Text>
          {queuedOnly.map((q) => (
            <View key={q.id} style={styles.queueItem}>
              <Text style={{ flex: 1, color: colors.text }} numberOfLines={1}>
                {q.content}
              </Text>
              <TouchableOpacity
                style={styles.queueBtn}
                onPress={() => prioritize(q.id)}
                accessibilityLabel="Ưu tiên lên đầu"
              >
                <Text style={{ color: colors.primary, fontWeight: "700" }}>⬆</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.queueBtn}
                onPress={() => cancelQueued(q.id)}
                accessibilityLabel="Hủy yêu cầu"
              >
                <Text style={{ color: colors.danger, fontWeight: "700" }}>✕</Text>
              </TouchableOpacity>
            </View>
          ))}
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
            <Text style={{ color: item.kind === "user" ? colors.onPrimary : colors.text }}>
              {item.text}
              {item.kind === "streaming" ? " ▍" : ""}
            </Text>
          </View>
        )}
      />
      {pendingConfirm && (
        <View style={styles.confirmBar}>
          <Text style={{ marginBottom: spacing.sm, color: colors.text }}>
            AI muốn thực hiện hành động nhạy cảm: {pendingConfirm.toolName}. Xác nhận?
          </Text>
          <View style={{ flexDirection: "row", gap: spacing.md }}>
            <TouchableOpacity style={styles.okBtn} onPress={() => resolveConfirm(true)}>
              <Text style={{ color: colors.onPrimary }}>Đồng ý</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.denyBtn} onPress={() => resolveConfirm(false)}>
              <Text style={{ color: colors.onPrimary }}>Từ chối</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}
      <View style={styles.inputBar}>
        <TextInput
          style={styles.input}
          placeholder="Nhắn cho trợ lý AI… (gửi không cần chờ)"
          placeholderTextColor={colors.textMuted}
          value={input}
          onChangeText={setInput}
          onSubmitEditing={submit}
          multiline
        />
        <TouchableOpacity style={styles.sendBtn} onPress={submit}>
          <Text style={{ color: colors.onPrimary, fontWeight: "700" }}>Gửi</Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  queueBar: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.warningBarBg,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  queueList: {
    backgroundColor: colors.warningBg,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderColor: colors.warningBorder,
  },
  queueTitle: {
    ...type.caption,
    fontWeight: "700",
    color: colors.warningText,
    marginBottom: spacing.xs,
  },
  queueItem: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.xs, gap: spacing.sm },
  queueBtn: { paddingHorizontal: spacing.sm, paddingVertical: spacing.xs },
  bubble: { borderRadius: radius.lg, padding: spacing.md, maxWidth: "85%" },
  userBubble: { backgroundColor: colors.primary, alignSelf: "flex-end" },
  aiBubble: { backgroundColor: colors.surfaceAlt, alignSelf: "flex-start" },
  systemBubble: { backgroundColor: colors.dangerBg, alignSelf: "center" },
  confirmBar: {
    backgroundColor: colors.confirmBg,
    padding: spacing.md,
    borderTopWidth: 1,
    borderColor: colors.confirmBorder,
  },
  okBtn: {
    backgroundColor: colors.success,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  denyBtn: {
    backgroundColor: colors.danger,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  inputBar: {
    flexDirection: "row",
    alignItems: "flex-end",
    padding: spacing.md,
    gap: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  input: {
    flex: 1,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    maxHeight: 120,
    fontSize: type.body.fontSize,
    color: colors.text,
  },
  sendBtn: {
    backgroundColor: colors.primary,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
});
