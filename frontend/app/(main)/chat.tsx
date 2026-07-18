import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import {
  ChatRequest,
  Conversation,
  Message,
  RESUME_PHRASE,
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
import { ErrorText } from "../../src/ui/form";
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

const TOOL_LABELS: Record<string, string> = {
  create_project: "Tạo project",
  update_project: "Cập nhật project",
  list_projects: "Tra cứu project",
  create_task: "Tạo task",
  update_task: "Cập nhật task",
  list_tasks: "Tra cứu task",
  get_task: "Xem chi tiết task",
  assign_task: "Gán người vào task",
  unassign_task: "Bỏ gán task",
  add_task_update: "Cập nhật tiến độ",
  list_task_updates: "Tra lịch sử cập nhật",
  add_comment: "Thêm bình luận",
  list_comments: "Tra bình luận",
  create_skill: "Tạo skill",
  add_skill_version: "Cập nhật skill",
  grant_skill: "Cấp quyền skill",
  list_skills: "Tra cứu skill",
  use_skill: "Dùng skill",
  list_skill_grants: "Tra quyền skill",
  revoke_skill_grant: "Thu hồi quyền skill",
  list_users: "Tra danh bạ",
  create_invite: "Tạo lời mời",
  lock_user: "Khóa tài khoản",
  unlock_user: "Mở khóa tài khoản",
  offboard_user: "Cho nghỉ việc",
  change_user_role: "Đổi vai trò",
  generate_report: "Tạo báo cáo",
  list_reports: "Tra báo cáo",
  create_report_schedule: "Tạo lịch báo cáo",
  list_report_schedules: "Tra lịch báo cáo",
  delete_report_schedule: "Hủy lịch báo cáo",
  list_audit_events: "Tra nhật ký",
  send_email: "Gửi email",
  create_instruction: "Tạo chỉ dẫn",
  update_instruction: "Cập nhật chỉ dẫn",
  list_instructions: "Tra chỉ dẫn",
  delete_instruction: "Xóa chỉ dẫn",
  list_portal_reports: "Tra báo cáo cổng CEO",
  get_portal_report: "Đọc báo cáo cổng CEO",
  list_voice_notes: "Tra ghi âm",
  get_voice_note: "Đọc ghi âm",
  list_task_attachments: "Tra tài liệu đính kèm",
  get_today_dashboard: "Tổng hợp hôm nay",
  create_note: "Tạo ghi chú",
  list_notes: "Tra ghi chú",
  search: "Tìm kiếm",
  list_notifications: "Tra thông báo",
  get_notification_preferences: "Tra cài đặt thông báo",
  set_notification_preference: "Đổi cài đặt thông báo",
};

function labelForTool(name: string): string {
  return TOOL_LABELS[name] ?? name.replace(/_/g, " ");
}

export default function Chat() {
  const { id: requestedId } = useLocalSearchParams<{ id?: string }>();
  const router = useRouter();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversationTitle, setConversationTitle] = useState<string | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [queue, setQueue] = useState<ChatRequest[]>([]);
  const [held, setHeld] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [pendingConfirm, setPendingConfirm] = useState<{
    requestId: string;
    toolName: string;
  } | null>(null);
  const [runningTool, setRunningTool] = useState<string | null>(null);
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
      if (e.type === "tool_running") {
        setRunningTool(labelForTool(e.tool_name));
        return;
      }
      if (e.type === "token") {
        setRunningTool(null);
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
        setRunningTool(null);
        streamingText.current.delete(e.chat_request_id);
        setRows((prev) =>
          prev.map((r) =>
            r.key === `stream-${e.chat_request_id}` ? { ...r, kind: "assistant" } : r,
          ),
        );
        refreshQueue(cid);
      } else if (e.type === "request_failed") {
        setRunningTool(null);
        setRows((prev) => [
          ...prev,
          { key: `fail-${e.chat_request_id}`, kind: "system", text: `⚠️ Yêu cầu lỗi: ${e.error} — các yêu cầu sau vẫn chạy tiếp.` },
        ]);
        refreshQueue(cid);
      } else if (e.type === "confirmation_required") {
        setRunningTool(null);
        setPendingConfirm({ requestId: e.chat_request_id, toolName: e.tool_name });
        refreshQueue(cid);
      } else if (e.type === "status_update") {
        refreshQueue(cid);
      }
    },
    [refreshQueue],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    setRows([]);
    setQueue([]);
    setHeld(false);
    setConversationTitle(null);
    closeWs.current?.();
    (async () => {
      try {
        const convs = await listConversations();
        let conv: Conversation | undefined;
        if (requestedId) {
          conv = convs.find((c) => c.id === requestedId);
          if (!conv) throw new Error("Không tìm thấy cuộc trò chuyện này");
        } else {
          conv = convs[0] ?? (await createConversation("Cuộc trò chuyện đầu tiên"));
        }
        if (cancelled) return;
        setConversationId(conv.id);
        setConversationTitle(conv.title);
        setHeld(conv.queue_held);
        await loadHistory(conv.id);
        await refreshQueue(conv.id);
        closeWs.current = await openConversationStream(conv.id, onWsEvent(conv.id));
      } catch (e: any) {
        if (!cancelled) setLoadError(String(e?.message ?? e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      closeWs.current?.();
    };
  }, [requestedId, loadHistory, onWsEvent, refreshQueue]);

  const submit = async () => {
    if (!conversationId || !input.trim()) return;
    const content = input.trim();
    setInput("");
    const req = await sendMessage(conversationId, content);
    if (held && content.toLowerCase() === RESUME_PHRASE) setHeld(false);
    setRows((prev) => [...prev, { key: `u-${req.id}`, kind: "user", text: content }]);
    await refreshQueue(conversationId);
  };

  const resumeQueue = async () => {
    if (!conversationId) return;
    const req = await sendMessage(conversationId, RESUME_PHRASE);
    setHeld(false);
    setRows((prev) => [...prev, { key: `u-${req.id}`, kind: "user", text: RESUME_PHRASE }]);
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
      <View style={styles.headerBar}>
        <Text style={{ flex: 1, color: colors.textSecondary }} numberOfLines={1}>
          {conversationTitle || "Cuộc trò chuyện"}
        </Text>
        <TouchableOpacity onPress={() => router.push("/conversations")}>
          <Text style={{ color: colors.primary, fontWeight: "700" }}>🗂 Lịch sử</Text>
        </TouchableOpacity>
      </View>
      <ErrorText error={loadError} />
      {held && (
        <View style={styles.heldBar}>
          <Text style={{ flex: 1, color: colors.warningText }}>
            ⏸ Việc dang dở đang chờ — gõ “{RESUME_PHRASE}” để AI làm nốt
          </Text>
          <TouchableOpacity
            style={styles.resumeBtn}
            onPress={resumeQueue}
            accessibilityLabel="Tiếp tục công việc"
          >
            <Text style={{ color: colors.onPrimary, fontWeight: "700" }}>▶ Tiếp tục</Text>
          </TouchableOpacity>
        </View>
      )}
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
        ListEmptyComponent={
          loading ? (
            <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
          ) : (
            <Text style={styles.emptyChat}>
              Chưa có tin nhắn — nhắn cho AI để giao việc, hỏi tiến độ, tạo note…
            </Text>
          )
        }
        contentContainerStyle={{ padding: spacing.md, gap: spacing.sm }}
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
      {runningTool && !pendingConfirm && (
        <View style={styles.toolBar}>
          <ActivityIndicator color={colors.primary} size="small" />
          <Text style={{ color: colors.textSecondary }}>Đang {runningTool}…</Text>
        </View>
      )}
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
  headerBar: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderColor: colors.divider,
    backgroundColor: colors.surface,
  },
  heldBar: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.warningBg,
    borderBottomWidth: 1,
    borderColor: colors.warningBorder,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  resumeBtn: {
    backgroundColor: colors.primary,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
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
  emptyChat: { color: colors.textMuted, textAlign: "center", marginTop: spacing.xxl },
  toolBar: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.surfaceAlt,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
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
