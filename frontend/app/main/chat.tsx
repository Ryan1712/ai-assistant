import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Keyboard,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import { Ionicons } from "@expo/vector-icons";
import { useNavigation, useRoute } from "@react-navigation/native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Markdown from "react-native-markdown-display";
import * as DocumentPicker from "expo-document-picker";
import { useAudioPlayer, useAudioPlayerStatus } from "expo-audio";
import { uploadVoiceNote, voiceNoteAudioSource } from "../../src/api/voice";
import { DictationButton } from "../../src/voice/DictationButton";
import {
  ChatRequest,
  Message,
  ProposedAction,
  RESUME_PHRASE,
  cancelRequest,
  confirmRequest,
  getActiveConversation,
  getTimeline,
  isResumePhrase,
  listConversations,
  listMessages,
  listRequests,
  reorderRequest,
  sendMessage,
  stopAll,
} from "../../src/api/chat";
import { WsEvent, openConversationStream } from "../../src/api/ws";
import { ErrorText } from "../../src/ui/form";
import { colors, fonts, radius, shadow, spacing, type } from "../../src/ui/theme";

type Row =
  | { key: string; kind: "user" | "assistant"; text: string; voiceNoteId?: string | null }
  | { key: string; kind: "streaming"; text: string }
  | { key: string; kind: "system"; text: string }
  | { key: string; kind: "failed"; text: string; retryContent: string | null };

function friendlyError(raw: string): string {
  if (raw.includes("max_iterations_exceeded"))
    return "AI chạy quá nhiều bước mà chưa xong — thử chia nhỏ yêu cầu.";
  if (raw.includes("max_tool_calls_exceeded"))
    return "AI đã gọi quá nhiều tool cho yêu cầu này — thử chia nhỏ yêu cầu.";
  if (raw.includes("max_duration_exceeded"))
    return "Yêu cầu xử lý quá lâu (có thể do hệ thống AI đang chậm) — thử lại sau.";
  if (raw.includes("max_total_tokens_exceeded"))
    return "Yêu cầu này cần xử lý quá nhiều dữ liệu — thử chia nhỏ yêu cầu.";
  if (raw.includes("max_tokens")) return "Câu trả lời quá dài bị cắt.";
  return `Có lỗi khi xử lý (${raw.slice(0, 120)}).`;
}

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
  create_employee: "Tạo nhân viên mới",
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
  resolve_person: "Tra cứu người",
  resolve_task: "Tra cứu task",
  propose_actions: "Đề xuất hành động",
  create_directive: "Giao việc chính thức",
  get_directive_status: "Tra tình trạng việc đã giao",
  get_project_health: "Soi tình trạng project",
  get_progress_stats: "So sánh tiến độ kỳ này",
};

function labelForTool(name: string): string {
  return TOOL_LABELS[name] ?? name.replace(/_/g, " ");
}

// Dựng Row[] từ Message[] — dùng chung cho cả timeline (LIVE) lẫn history (xem lại).
// Chèn divider khi đổi conversation_id giữa 2 message liên tiếp (chỉ xảy ra ở timeline
// xuyên conversation, vì history luôn cùng 1 conversation_id).
function messagesToRows(msgs: Message[]): Row[] {
  const out: Row[] = [];
  let prevConv: string | null | undefined = undefined;
  for (const m of msgs) {
    if (prevConv !== undefined && m.conversation_id && m.conversation_id !== prevConv) {
      out.push({ key: `divider-${m.id}`, kind: "system", text: "— cuộc trò chuyện mới —" });
    }
    prevConv = m.conversation_id ?? prevConv;
    const text = textOfMessage(m);
    if (text)
      out.push({ key: m.id, kind: m.role === "user" ? "user" : "assistant", text,
                 voiceNoteId: m.voice_note_id });
    // Lượt AI thuần thao tác (tạo task, gán người...) không có text — trước đây
    // biến mất khỏi lịch sử, người dùng mất dấu "AI đã làm gì".
    for (const b of m.content) {
      if (b.type === "tool_use")
        out.push({ key: `${m.id}-${b.id}`, kind: "system", text: labelForTool(b.name) });
    }
  }
  return out;
}

const mdStyles = {
  body: { color: colors.text, fontSize: 16, lineHeight: 26, fontFamily: fonts.regular },
  strong: { fontFamily: fonts.bold },
  heading1: { fontFamily: fonts.bold, color: colors.text },
  heading2: { fontFamily: fonts.bold, color: colors.text },
  heading3: { fontFamily: fonts.semibold, color: colors.text },
  code_inline: { backgroundColor: colors.surfaceAlt, color: colors.text, borderRadius: 4 },
  fence: { backgroundColor: colors.surfaceAlt, borderColor: colors.divider, color: colors.text, borderRadius: radius.md },
  code_block: { backgroundColor: colors.surfaceAlt, borderColor: colors.divider, color: colors.text, borderRadius: radius.md },
  table: { borderColor: colors.divider },
  link: { color: colors.primary },
} as const;

export default function Chat() {
  const { id: requestedId } = (useRoute<any>().params ?? {}) as { id?: string };
  const navigation = useNavigation<any>();
  const insets = useSafeAreaInsets();
  const [kbVisible, setKbVisible] = useState(false);
  useEffect(() => {
    const s = Keyboard.addListener("keyboardWillShow", () => setKbVisible(true));
    const h = Keyboard.addListener("keyboardWillHide", () => setKbVisible(false));
    return () => {
      s.remove();
      h.remove();
    };
  }, []);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [conversationTitle, setConversationTitle] = useState<string | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [queue, setQueue] = useState<ChatRequest[]>([]);
  const [held, setHeld] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [archived, setArchived] = useState(false); // conv đang xem đã lưu trữ?
  const [historyMode, setHistoryMode] = useState(false); // mở theo ?id (xem lại)?
  const [olderCursor, setOlderCursor] = useState<{ at: string; id: string } | null>(null);
  const [hasMoreOlder, setHasMoreOlder] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [input, setInput] = useState("");
  type PendingConfirm =
    | { requestId: string; kind: "tool"; toolName: string; toolInput: Record<string, unknown> }
    | { requestId: string; kind: "proposal"; actions: ProposedAction[]; reasoning: string };
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirm | null>(null);
  const [runningTool, setRunningTool] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [attachedAudio, setAttachedAudio] = useState<{ uri: string; name: string } | null>(null);
  const [audioPlayingId, setAudioPlayingId] = useState<string | null>(null);
  const audioPlayer = useAudioPlayer(null);
  const audioStatus = useAudioPlayerStatus(audioPlayer);
  const streamingText = useRef<Map<string, string>>(new Map());
  const contentByRequest = useRef<Map<string, string>>(new Map());
  const listRef = useRef<FlatList>(null);
  const closeWs = useRef<(() => void) | null>(null);

  const refreshQueue = useCallback(async (cid: string) => {
    const reqs = await listRequests(cid);
    reqs.forEach((r) => contentByRequest.current.set(r.id, r.content));
    setQueue(reqs.filter((r) => r.status === "queued" || r.status === "running"));
    const waiting = reqs.find((r) => r.status === "awaiting_confirmation");
    if (waiting) {
      const action = waiting.pending_action;
      if (action?.kind === "proposal") {
        setPendingConfirm({
          requestId: waiting.id,
          kind: "proposal",
          actions: action.actions,
          reasoning: action.reasoning,
        });
      } else {
        setPendingConfirm({
          requestId: waiting.id,
          kind: "tool",
          toolName: action?.tool_name ?? "unknown",
          toolInput: (action?.tool_input ?? {}) as Record<string, unknown>,
        });
      }
    }
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
        const retryContent = contentByRequest.current.get(e.chat_request_id) ?? null;
        setRows((prev) => [
          ...prev,
          {
            key: `fail-${e.chat_request_id}`,
            kind: "failed",
            text: friendlyError(e.error),
            retryContent,
          },
        ]);
        refreshQueue(cid);
      } else if (e.type === "confirmation_required") {
        setRunningTool(null);
        if (e.kind === "proposal") {
          setPendingConfirm({
            requestId: e.chat_request_id,
            kind: "proposal",
            actions: e.actions,
            reasoning: e.reasoning,
          });
        } else {
          setPendingConfirm({
            requestId: e.chat_request_id,
            kind: "tool",
            toolName: e.tool_name,
            toolInput: (e.tool_input ?? {}) as Record<string, unknown>,
          });
        }
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
    setArchived(false);
    setOlderCursor(null);
    setHasMoreOlder(false);
    closeWs.current?.();
    (async () => {
      try {
        let convId: string;
        if (requestedId) {
          // History mode: xem lại 1 conversation cụ thể.
          setHistoryMode(true);
          const all = await listConversations();
          const conv = all.find((c) => c.id === requestedId);
          if (!conv) throw new Error("Không tìm thấy cuộc trò chuyện này");
          convId = conv.id;
          setConversationTitle(conv.title);
          setArchived(conv.archived_at != null);
          setHeld(conv.queue_held);
          const msgs = await listMessages(convId);
          if (cancelled) return;
          setRows(messagesToRows(msgs));
        } else {
          // LIVE mode: active conversation + timeline xuyên conversation.
          setHistoryMode(false);
          const active = await getActiveConversation();
          convId = active.id;
          setConversationTitle(active.title);
          setArchived(false);
          setHeld(active.queue_held);
          const LIMIT = 50;
          const page = await getTimeline({ limit: LIMIT });
          if (cancelled) return;
          const chrono = [...page].reverse(); // API newest-first -> hiển thị cũ→mới
          setRows(messagesToRows(chrono));
          if (page.length === LIMIT && page.length > 0) {
            const oldest = page[page.length - 1];
            setOlderCursor({ at: oldest.created_at, id: oldest.id });
            setHasMoreOlder(true);
          }
        }
        if (cancelled) return;
        setConversationId(convId);
        await refreshQueue(convId);
        closeWs.current = await openConversationStream(convId, onWsEvent(convId));
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
  }, [requestedId, onWsEvent, refreshQueue]);

  const loadOlder = async () => {
    if (!olderCursor || loadingOlder) return;
    setLoadingOlder(true);
    try {
      const LIMIT = 50;
      const page = await getTimeline({ beforeAt: olderCursor.at, beforeId: olderCursor.id, limit: LIMIT });
      const chrono = [...page].reverse();
      setRows((prev) => [...messagesToRows(chrono), ...prev]);
      if (page.length === LIMIT && page.length > 0) {
        const oldest = page[page.length - 1];
        setOlderCursor({ at: oldest.created_at, id: oldest.id });
      } else {
        setHasMoreOlder(false);
      }
    } catch {
      setActionError("Không tải được đoạn cũ hơn — thử lại.");
    } finally {
      setLoadingOlder(false);
    }
  };

  const submit = async () => {
    if (archived) return;
    if (!conversationId) return;
    const content = input.trim() || (attachedAudio ? "Xử lý file ghi âm này giúp tôi" : "");
    if (!content) return;
    setInput("");
    Keyboard.dismiss(); // ẩn bàn phím ngay khi gửi
    try {
      let voiceNoteId: string | undefined;
      if (attachedAudio) {
        // Upload qua endpoint voice-notes sẵn có → file tự nằm trong thư viện ghi âm
        const note = await uploadVoiceNote(attachedAudio.uri, {});
        voiceNoteId = note.id;
      }
      const req = await sendMessage(conversationId, content, voiceNoteId);
      contentByRequest.current.set(req.id, content);
      setAttachedAudio(null);
      if (held && isResumePhrase(content)) setHeld(false);
      setRows((prev) => [...prev, { key: `u-${req.id}`, kind: "user", text: content,
                                    voiceNoteId: voiceNoteId ?? null }]);
      requestAnimationFrame(() => listRef.current?.scrollToEnd({ animated: false }));
      await refreshQueue(conversationId);
    } catch (e: any) {
      setInput(content); // không được làm mất chữ người dùng vừa gõ (attachment cũng giữ)
      setRows((prev) => [
        ...prev,
        {
          key: `senderr-${Date.now()}`,
          kind: "system",
          text: `Gửi thất bại (${String(e?.message ?? e).slice(0, 80)}) — nội dung đã được giữ lại trong ô nhập.`,
        },
      ]);
    }
  };

  const pickAudio = async () => {
    try {
      const res = await DocumentPicker.getDocumentAsync({
        type: "audio/*",
        copyToCacheDirectory: true,
      });
      if (!res.canceled && res.assets?.[0]) {
        setAttachedAudio({ uri: res.assets[0].uri, name: res.assets[0].name });
      }
    } catch {
      setActionError("Không chọn được file — thử lại.");
    }
  };

  const toggleAudioBubble = async (voiceNoteId: string) => {
    try {
      if (audioPlayingId === voiceNoteId) {
        if (audioStatus.playing) audioPlayer.pause();
        else audioPlayer.play();
        return;
      }
      const source = await voiceNoteAudioSource(voiceNoteId);
      audioPlayer.replace(source);
      audioPlayer.play();
      setAudioPlayingId(voiceNoteId);
    } catch {
      setActionError("Không phát được ghi âm — thử lại.");
    }
  };

  const resumeQueue = async () => {
    if (archived) return;
    if (!conversationId) return;
    try {
      const req = await sendMessage(conversationId, RESUME_PHRASE);
      contentByRequest.current.set(req.id, RESUME_PHRASE);
      setHeld(false);
      setRows((prev) => [...prev, { key: `u-${req.id}`, kind: "user", text: RESUME_PHRASE }]);
      await refreshQueue(conversationId);
    } catch {
      setRows((prev) => [
        ...prev,
        { key: `resumeerr-${Date.now()}`, kind: "system", text: "Không gửi được — thử lại." },
      ]);
    }
  };

  const resolveConfirm = async (approved: boolean) => {
    if (!pendingConfirm || !conversationId) return;
    await confirmRequest(pendingConfirm.requestId, approved);
    setPendingConfirm(null);
    await refreshQueue(conversationId);
  };

  const doStopAll = async () => {
    if (!conversationId) return;
    setActionError(null);
    try {
      await stopAll(conversationId);
      await refreshQueue(conversationId);
    } catch {
      setActionError("Không dừng được — thử lại.");
    }
  };

  const cancelQueued = async (requestId: string) => {
    if (!conversationId) return;
    setActionError(null);
    try {
      await cancelRequest(requestId);
    } catch {
      setActionError("Thao tác thất bại — thử lại.");
    }
    await refreshQueue(conversationId);
  };

  const prioritize = async (requestId: string) => {
    if (!conversationId) return;
    setActionError(null);
    try {
      await reorderRequest(requestId, null); // before_id null = lên đầu hàng đợi
    } catch {
      setActionError("Thao tác thất bại — thử lại.");
    }
    await refreshQueue(conversationId);
  };

  const running = queue.find((q) => q.status === "running");
  const queuedOnly = queue.filter((q) => q.status === "queued");
  const canSend = input.trim().length > 0 || !!attachedAudio;

  const renderItem = ({ item }: { item: Row }) => {
    if (item.kind === "assistant" || item.kind === "streaming") {
      return (
        <View style={styles.assistantWrap}>
          <Markdown style={mdStyles}>
            {item.text + (item.kind === "streaming" ? " ▍" : "")}
          </Markdown>
        </View>
      );
    }
    if (item.kind === "user") {
      const playing = audioPlayingId === item.voiceNoteId && audioStatus.playing;
      return (
        <View style={styles.userWrap}>
          <View style={styles.userBubble}>
            <Text style={styles.userText}>{item.text}</Text>
            {item.voiceNoteId && (
              <TouchableOpacity
                onPress={() => toggleAudioBubble(item.voiceNoteId!)}
                style={styles.audioChip}
                accessibilityLabel="Phát ghi âm đính kèm"
              >
                <Ionicons name={playing ? "pause" : "play"} size={14} color={colors.text} />
                <Text style={styles.audioChipText}>Ghi âm đính kèm</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>
      );
    }
    // system (tool-use) hoặc failed — dòng phụ kiểu "thinking/tool" của Claude
    const failed = item.kind === "failed";
    return (
      <View style={[styles.systemRow, failed && styles.systemRowFailed]}>
        <Ionicons
          name={failed ? "alert-circle-outline" : "sparkles-outline"}
          size={15}
          color={failed ? colors.danger : colors.textSecondary}
        />
        <Text style={[styles.systemText, failed && { color: colors.danger }]} numberOfLines={2}>
          {item.text}
        </Text>
        {failed && item.retryContent && (
          <TouchableOpacity onPress={() => setInput(item.retryContent!)}>
            <Text style={styles.retryLink}>Gửi lại</Text>
          </TouchableOpacity>
        )}
      </View>
    );
  };

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: colors.surface }} behavior="padding">
      {/* Header tối giản kiểu Claude: menu · tiêu đề · (history mode: nút về luồng hiện tại) */}
      <View style={[styles.header, { paddingTop: insets.top + spacing.xs }]}>
        <TouchableOpacity
          style={styles.headerBtn}
          onPress={() => navigation.openDrawer()}
          accessibilityLabel="Menu"
        >
          <Ionicons name="menu-outline" size={26} color={colors.text} />
        </TouchableOpacity>
        <Text style={styles.headerTitle} numberOfLines={1}>
          {conversationTitle || "Trợ lý AI"}
        </Text>
        {historyMode ? (
          <TouchableOpacity
            style={styles.headerBtn}
            onPress={() => navigation.navigate("Chat", { id: undefined })}
            accessibilityLabel="Về luồng hiện tại"
          >
            <Ionicons name="arrow-undo-outline" size={22} color={colors.text} />
          </TouchableOpacity>
        ) : (
          <View style={styles.headerBtn} />
        )}
      </View>

      <ErrorText error={loadError} />

      {held && (
        <View style={styles.heldBar}>
          <Text style={styles.heldText}>
            ⏸ Việc dang dở đang chờ — gõ “{RESUME_PHRASE}” để AI làm nốt
          </Text>
          <TouchableOpacity style={styles.pillPrimary} onPress={resumeQueue} accessibilityLabel="Tiếp tục công việc">
            <Text style={styles.pillPrimaryText}>Tiếp tục</Text>
          </TouchableOpacity>
        </View>
      )}

      <ErrorText error={actionError} />

      <FlatList
        ref={listRef}
        data={rows}
        keyExtractor={(r) => r.key}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="interactive"
        ListHeaderComponent={
          !historyMode && hasMoreOlder ? (
            <TouchableOpacity style={styles.loadOlder} onPress={loadOlder} disabled={loadingOlder}>
              {loadingOlder ? (
                <ActivityIndicator color={colors.primary} size="small" />
              ) : (
                <Text style={styles.loadOlderText}>↑ Tải đoạn hội thoại cũ hơn</Text>
              )}
            </TouchableOpacity>
          ) : null
        }
        ListEmptyComponent={
          loading ? (
            <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxxl }} />
          ) : (
            <View style={styles.empty}>
              <Ionicons name="sparkles" size={30} color={colors.primary} />
              <Text style={styles.emptyText}>
                Nhắn cho trợ lý để giao việc, hỏi tiến độ, tạo note… — gửi không cần chờ.
              </Text>
            </View>
          )
        }
        contentContainerStyle={styles.listContent}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: false })}
        renderItem={renderItem}
      />

      {runningTool && !pendingConfirm && (
        <View style={styles.working}>
          <ActivityIndicator color={colors.primary} size="small" />
          <Text style={styles.workingText}>Đang {runningTool}…</Text>
        </View>
      )}
      {running && !runningTool && !pendingConfirm && !streamingText.current.get(running.id) && (
        <View style={styles.working}>
          <ActivityIndicator color={colors.primary} size="small" />
          <Text style={styles.workingText}>AI đang soạn…</Text>
        </View>
      )}
      {pendingConfirm && pendingConfirm.kind === "proposal" && (
        <View style={styles.confirmBar}>
          <Text style={styles.confirmTitle}>⚠️ AI muốn thực hiện:</Text>
          {pendingConfirm.actions.map((a, i) => (
            <Text key={i} style={styles.confirmDetail}>
              {i + 1}. {a.display_text}
            </Text>
          ))}
          {pendingConfirm.reasoning ? (
            <Text style={[styles.confirmDetail, { fontStyle: "italic", color: colors.textSecondary }]}>
              {pendingConfirm.reasoning}
            </Text>
          ) : null}
          <Text style={styles.confirmAsk}>Xác nhận thực hiện?</Text>
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <TouchableOpacity style={styles.pillPrimary} onPress={() => resolveConfirm(true)}>
              <Text style={styles.pillPrimaryText}>Đồng ý</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.pillGhostDanger} onPress={() => resolveConfirm(false)}>
              <Text style={styles.pillGhostDangerText}>Từ chối</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}
      {pendingConfirm && pendingConfirm.kind === "tool" && (
        <View style={styles.confirmBar}>
          <Text style={styles.confirmTitle}>AI muốn: {labelForTool(pendingConfirm.toolName)}</Text>
          {Object.entries(pendingConfirm.toolInput).map(([k, v]) => (
            <Text key={k} style={styles.confirmDetail}>
              • {k}: {typeof v === "object" ? JSON.stringify(v) : String(v)}
            </Text>
          ))}
          <Text style={styles.confirmAsk}>Xác nhận thực hiện?</Text>
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <TouchableOpacity style={styles.pillPrimary} onPress={() => resolveConfirm(true)}>
              <Text style={styles.pillPrimaryText}>Đồng ý</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.pillGhostDanger} onPress={() => resolveConfirm(false)}>
              <Text style={styles.pillGhostDangerText}>Từ chối</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {/* Composer kiểu Claude: card bo tròn, input trên, hàng nút dưới (bỏ chọn model) */}
      {historyMode && archived ? (
        <View style={styles.readonlyBar}>
          <Text style={styles.readonlyText}>Cuộc trò chuyện đã lưu trữ — chỉ xem lại.</Text>
          <TouchableOpacity
            style={styles.pillPrimary}
            onPress={() => navigation.navigate("Chat", { id: undefined })}
          >
            <Text style={styles.pillPrimaryText}>Về luồng hiện tại</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <View style={[styles.composerWrap, { paddingBottom: kbVisible ? spacing.sm : insets.bottom || spacing.sm }]}>
          <View style={styles.composerCard}>
            {attachedAudio && (
              <View style={styles.attachChip}>
                <Ionicons name="mic" size={16} color={colors.primary} />
                <Text style={{ flex: 1, color: colors.text, fontFamily: fonts.medium }} numberOfLines={1}>
                  {attachedAudio.name}
                </Text>
                <TouchableOpacity onPress={() => setAttachedAudio(null)} accessibilityLabel="Bỏ đính kèm" hitSlop={8}>
                  <Ionicons name="close" size={18} color={colors.textSecondary} />
                </TouchableOpacity>
              </View>
            )}
            <TextInput
              style={styles.input}
              placeholder="Nhắn cho trợ lý AI…"
              placeholderTextColor={colors.textMuted}
              value={input}
              onChangeText={setInput}
              multiline
            />
            <View style={styles.composerRow}>
              <TouchableOpacity style={styles.plusBtn} onPress={pickAudio} accessibilityLabel="Đính kèm file ghi âm">
                <Ionicons name="add" size={26} color={colors.textSecondary} />
              </TouchableOpacity>
              <View style={{ flex: 1 }} />
              <DictationButton onText={(t) => setInput(t)} />
              <TouchableOpacity
                style={[styles.sendBtn, !canSend && styles.sendBtnOff]}
                onPress={submit}
                disabled={!canSend}
                accessibilityLabel="Gửi"
              >
                <Ionicons name="arrow-up" size={20} color={canSend ? colors.onPrimary : colors.textMuted} />
              </TouchableOpacity>
            </View>
          </View>
        </View>
      )}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.sm,
    paddingBottom: spacing.sm,
    backgroundColor: colors.surface,
  },
  headerBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontFamily: fonts.semibold, fontSize: 16, color: colors.text },

  listContent: { paddingHorizontal: spacing.lg, paddingVertical: spacing.lg, gap: spacing.lg },

  // Tin nhắn AI: chữ thuần, full-width (không bong bóng) — như Claude
  assistantWrap: { paddingRight: spacing.sm },

  // Tin nhắn người dùng: bong bóng xám trung tính, canh phải
  userWrap: { alignItems: "flex-end" },
  userBubble: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.xl,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    maxWidth: "88%",
  },
  userText: { color: colors.text, fontSize: 16, lineHeight: 23, fontFamily: fonts.regular },
  audioChip: { flexDirection: "row", alignItems: "center", gap: spacing.xs, marginTop: spacing.sm },
  audioChipText: { color: colors.text, fontFamily: fonts.semibold, fontSize: 13 },

  // Dòng tool-use / lỗi — nhỏ, mờ, kiểu "thinking row"
  systemRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    alignSelf: "flex-start",
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    maxWidth: "92%",
  },
  systemRowFailed: { backgroundColor: colors.dangerBg },
  systemText: { color: colors.textSecondary, fontFamily: fonts.medium, fontSize: 13, flexShrink: 1 },
  retryLink: { color: colors.primary, fontFamily: fonts.semibold, fontSize: 13 },

  empty: { alignItems: "center", gap: spacing.md, marginTop: spacing.xxxl, paddingHorizontal: spacing.xl },
  emptyText: { color: colors.textMuted, textAlign: "center", fontSize: 15, lineHeight: 22, fontFamily: fonts.regular },

  working: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  workingText: { color: colors.textSecondary, fontFamily: fonts.medium, fontSize: 14 },

  heldBar: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.warningBg,
    borderTopWidth: 1,
    borderBottomWidth: 1,
    borderColor: colors.warningBorder,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  heldText: { flex: 1, color: colors.warningText, fontFamily: fonts.medium, fontSize: 13 },

  loadOlder: { alignItems: "center", paddingVertical: spacing.md },
  loadOlderText: { color: colors.primary, fontFamily: fonts.semibold, fontSize: 14 },

  readonlyBar: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    backgroundColor: colors.surfaceAlt,
  },
  readonlyText: { flex: 1, color: colors.textSecondary, fontFamily: fonts.medium, fontSize: 13 },

  queueBar: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.surfaceAlt,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  queueList: {
    backgroundColor: colors.surfaceAlt,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderColor: colors.divider,
  },
  queueTitle: { ...type.caption, fontFamily: fonts.bold, color: colors.textSecondary, marginBottom: spacing.xs },
  queueItem: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.xs, gap: spacing.sm },
  queueBtn: { padding: spacing.xs },
  dangerLink: { color: colors.danger, fontFamily: fonts.semibold, fontSize: 14 },

  confirmBar: {
    backgroundColor: colors.confirmBg,
    padding: spacing.lg,
    borderTopWidth: 1,
    borderColor: colors.confirmBorder,
  },
  confirmTitle: { fontFamily: fonts.bold, fontSize: 15, marginBottom: spacing.xs, color: colors.text },
  confirmDetail: { color: colors.text, fontSize: 14, lineHeight: 20 },
  confirmAsk: { marginVertical: spacing.sm, color: colors.text, fontFamily: fonts.medium },

  // Nút pill dùng chung
  pillPrimary: {
    backgroundColor: colors.primary,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    alignItems: "center",
    justifyContent: "center",
  },
  pillPrimaryText: { color: colors.onPrimary, fontFamily: fonts.bold, fontSize: 14 },
  pillGhostDanger: {
    borderRadius: radius.pill,
    borderWidth: 1.5,
    borderColor: colors.danger,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm - 1.5,
    alignItems: "center",
    justifyContent: "center",
  },
  pillGhostDangerText: { color: colors.danger, fontFamily: fonts.bold, fontSize: 14 },

  // Composer
  composerWrap: { paddingHorizontal: spacing.md, paddingTop: spacing.xs, backgroundColor: colors.surface },
  composerCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.xl,
    borderWidth: 1,
    borderColor: colors.borderStrong,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
    ...shadow.soft,
  },
  attachChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    marginBottom: spacing.sm,
  },
  input: {
    fontSize: 16,
    lineHeight: 22,
    color: colors.text,
    fontFamily: fonts.regular,
    maxHeight: 140,
    paddingHorizontal: spacing.xs,
    paddingTop: spacing.xs,
    paddingBottom: spacing.xs,
  },
  composerRow: { flexDirection: "row", alignItems: "center", marginTop: spacing.xs },
  plusBtn: { width: 36, height: 36, alignItems: "center", justifyContent: "center" },
  sendBtn: {
    width: 36,
    height: 36,
    borderRadius: radius.pill,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    marginLeft: spacing.xs,
  },
  sendBtnOff: { backgroundColor: colors.surfaceAlt },
});
