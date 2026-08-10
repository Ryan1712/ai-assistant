/**
 * ProjectCard — thẻ hiển thị thông tin 1 project trong danh sách.
 *
 * UX:
 *  - Tap vào THÂN THẺ (flex-1, bên trái) = mở chat mới gắn vào project (gắn mềm qua PATCH).
 *  - Tap vào CHEVRON (bên phải, sibling) = xổ/thu gọn danh sách task.
 *  - Tap vào 1 task trong danh sách = vào TaskDetail như cũ.
 *
 * Kiến trúc: nội dung thẻ và chevron là 2 touchable SIBLING nằm trong 1 hàng
 * (không lồng nhau) → tránh nested-touchable không đáng tin cậy trong RN + tests.
 */
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { Ionicons } from "@expo/vector-icons";
import { Project } from "../../src/api/projects";
import { TaskDetail } from "../../src/api/tasks";
import { createConversation, updateConversation } from "../../src/api/chat";
import { colors, radius, spacing, type } from "../../src/ui/theme";

const STATUS_LABEL: Record<string, string> = {
  active: "Đang chạy",
  completed: "Hoàn thành",
  on_hold: "Tạm dừng",
};

type Props = { p: Project; tasks: TaskDetail[] };

export function ProjectCard({ p, tasks }: Props) {
  const navigation = useNavigation<any>();
  const [expanded, setExpanded] = useState(false);
  const done = tasks.filter((t) => t.status === "done").length;
  const percent = tasks.length > 0 ? Math.round((done / tasks.length) * 100) : 0;

  /**
   * Mở chat gắn vào project theo model "gắn mềm" của BE:
   * tạo conversation mới rồi PATCH project_id (không find-or-create, không khóa cứng
   * — project chỉ là default cho create_task, gắn/gỡ/đổi được qua modal sửa tên).
   */
  const openChat = async () => {
    try {
      const conv = await createConversation();
      await updateConversation(conv.id, { project_id: p.id });
      navigation.navigate("Chat", { id: conv.id });
    } catch {
      // Lỗi mạng / server → không crash, không navigate.
    }
  };

  return (
    <View style={styles.card}>
      {/* Hàng trên: nội dung chính (flex-1) + chevron (fixed-width), SIBLING nhau */}
      <View style={styles.topRow}>
        {/* Vùng nội dung chính: tap = mở chat */}
        <TouchableOpacity
          style={styles.contentArea}
          activeOpacity={0.75}
          onPress={openChat}
          accessibilityLabel={`Mở chat project ${p.name}`}
        >
          <View style={styles.titleRow}>
            <Text style={styles.cardTitle} numberOfLines={1}>
              {p.name}
            </Text>
            <View style={styles.badge}>
              <Text style={styles.badgeText}>{STATUS_LABEL[p.status] ?? p.status}</Text>
            </View>
          </View>
          {p.goal !== "" && (
            <Text style={styles.subText} numberOfLines={2}>
              {p.goal}
            </Text>
          )}
          <Text style={styles.subText}>
            {done}/{tasks.length} task hoàn thành ({percent}%)
            {p.deadline && ` — Hạn: ${new Date(p.deadline).toLocaleDateString("vi-VN")}`}
          </Text>
        </TouchableOpacity>

        {/* Chevron: sibling, tap = xổ/thu gọn danh sách task.
            Dùng Pressable thay TouchableOpacity để onPress được expose trực tiếp
            lên host component — đáng tin cậy hơn trong RNTL khi không có children hữu hình. */}
        <Pressable
          onPress={() => setExpanded((e) => !e)}
          hitSlop={8}
          accessibilityLabel={expanded ? "Thu gọn danh sách task" : "Xem danh sách task"}
          style={styles.chevronBtn}
        >
          <Ionicons
            name={expanded ? "chevron-up-outline" : "chevron-down-outline"}
            size={18}
            color={colors.textSecondary}
          />
        </Pressable>
      </View>

      {/* Danh sách task — chỉ hiện khi expanded */}
      {expanded && (
        <View style={styles.taskListWrap}>
          {tasks.length === 0 && (
            <Text style={styles.emptyTaskText}>Chưa có task trong project này</Text>
          )}
          {tasks.map((t) => (
            <TouchableOpacity
              key={t.id}
              style={styles.taskRow}
              onPress={() => navigation.navigate("TaskDetail", { id: t.id })}
            >
              <Text style={styles.taskTitle} numberOfLines={1}>
                {t.title}
              </Text>
              <Text style={styles.taskPercent}>{t.percent}%</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
  },
  topRow: {
    flexDirection: "row",
    alignItems: "flex-start",
  },
  contentArea: { flex: 1 },
  titleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
  },
  cardTitle: { ...type.heading, flex: 1 },
  badge: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  badgeText: { color: colors.textSecondary, fontSize: type.caption.fontSize, fontWeight: "700" },
  subText: { color: colors.textSecondary, marginTop: spacing.xs },
  chevronBtn: {
    paddingLeft: spacing.sm,
    paddingTop: spacing.xs,
    minWidth: 30,
    alignItems: "center",
  },
  taskListWrap: { marginTop: spacing.sm },
  emptyTaskText: { color: colors.textMuted },
  taskRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
  taskTitle: { flex: 1 },
  taskPercent: { color: colors.textSecondary },
});
