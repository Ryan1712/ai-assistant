// ChatRow — component con memo hoá cho FlatList trong màn Chat.
// Đặt riêng file để React.memo hoạt động đúng (không bị tạo lại mỗi render
// của component cha). Props tối thiểu; handlers stable qua useCallback ở Chat.
import React from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import Markdown from "react-native-markdown-display";
import { colors, fonts, radius, spacing } from "../../src/ui/theme";
import type { Row } from "./chatTypes";

export type ChatRowProps = {
  item: Row;
  audioPlayingId: string | null;
  audioPlaying: boolean;
  onSubmit: (text: string) => void;
  onToggleAudio: (voiceNoteId: string) => void;
  onRetry: (text: string) => void;
};

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

const ChatRow = React.memo(function ChatRow({
  item,
  audioPlayingId,
  audioPlaying,
  onSubmit,
  onToggleAudio,
  onRetry,
}: ChatRowProps) {
  if (item.kind === "streaming") {
    // Text thô, KHÔNG qua Markdown — trong lúc stream, chuỗi thường xuyên ở
    // trạng thái markdown chưa cân bằng (vd mới có 1 dấu "**" của in đậm,
    // chưa có dấu đóng). react-native-markdown-display là CommonMark parser
    // thường, không thiết kế cho input đang chạy dần — parse chuỗi lệch cú
    // pháp có thể throw giữa chừng (bug thật: 2026-07-27). Chỉ parse Markdown
    // khi tin nhắn hoàn tất (kind chuyển "assistant" ở request_done).
    return (
      <View style={styles.assistantWrap}>
        <Text style={mdStyles.body}>{item.text} ▍</Text>
      </View>
    );
  }
  if (item.kind === "assistant") {
    return (
      <View style={styles.assistantWrap}>
        <Markdown style={mdStyles}>{item.text}</Markdown>
      </View>
    );
  }
  if (item.kind === "user") {
    const playing = audioPlayingId === item.voiceNoteId && audioPlaying;
    return (
      <View style={styles.userWrap}>
        <View style={styles.userBubble}>
          <Text style={styles.userText}>{item.text}</Text>
          {item.voiceNoteId && (
            <TouchableOpacity
              onPress={() => onToggleAudio(item.voiceNoteId!)}
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
  if (item.kind === "choices") {
    return (
      <View style={styles.choicesRow}>
        {item.options.map((opt, i) => (
          <TouchableOpacity
            key={`${item.key}-${i}`}
            style={styles.chip}
            onPress={() => onSubmit(opt)}
          >
            <Text style={styles.chipText}>{opt}</Text>
          </TouchableOpacity>
        ))}
      </View>
    );
  }
  // system (tool-use) hoặc failed
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
        <TouchableOpacity onPress={() => onRetry(item.retryContent!)}>
          <Text style={styles.retryLink}>Gửi lại</Text>
        </TouchableOpacity>
      )}
    </View>
  );
});

export default ChatRow;

const styles = StyleSheet.create({
  assistantWrap: { paddingRight: spacing.sm },
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
  choicesRow: {
    flexDirection: "row", flexWrap: "wrap", gap: spacing.sm,
  },
  chip: {
    backgroundColor: colors.surfaceAlt, borderWidth: 1, borderColor: colors.borderStrong,
    borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
  },
  chipText: { color: colors.text, fontFamily: fonts.semibold, fontSize: 13 },
});
