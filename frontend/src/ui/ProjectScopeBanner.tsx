/**
 * ProjectScopeBanner — chip/banner hiển thị khi cuộc chat đang scoped vào 1 project.
 * Không hiển thị gì khi projectId null (cuộc chat thường).
 *
 * Props:
 *  projectId  — id project đang scope; null → không render.
 *  projectName — tên project (async, có thể null khi đang tải).
 */
import React from "react";
import { StyleSheet, Text, View } from "react-native";
import { colors, fonts, spacing, type } from "./theme";

type Props = {
  projectId: string | null;
  projectName: string | null;
};

export function ProjectScopeBanner({ projectId, projectName }: Props) {
  if (!projectId) return null;
  return (
    <View style={styles.banner}>
      <Text style={styles.text} numberOfLines={1}>
        {"🔒 Đang trong project: "}
        <Text style={styles.name}>{projectName ?? "đang tải..."}</Text>
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.primaryTint,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderColor: colors.divider,
  },
  // Dùng type.label (fontSize 13, semibold) làm base; override font weight (medium cho nhãn)
  // và màu (primaryDeep thay textSecondary).
  text: {
    ...type.label,
    flex: 1,
    fontFamily: fonts.medium,   // nhẹ hơn semibold — phần nhãn "Đang trong project:"
    color: colors.primaryDeep,
  },
  // Tên project: semibold (giữ nguyên từ type.label), chỉ override màu
  name: {
    ...type.label,
    color: colors.primaryDeep,
  },
});
