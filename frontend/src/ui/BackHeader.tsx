import React from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useRouter } from "expo-router";
import { colors, spacing } from "./theme";

/** Header dùng chung cho mọi route ẩn (push từ Cài đặt/màn khác) — các route này
 * không nằm trong tab bar nên không có cách nào khác để quay lại. */
export function BackHeader({ title, fallback = "/today" }: { title: string; fallback?: string }) {
  const router = useRouter();
  return (
    <View style={styles.headerBar}>
      <TouchableOpacity
        onPress={() => (router.canGoBack() ? router.back() : router.replace(fallback))}
        accessibilityLabel="Quay lại"
      >
        <Text style={{ color: colors.primary, fontWeight: "700" }}>← Quay lại</Text>
      </TouchableOpacity>
      <Text style={styles.title} numberOfLines={1}>
        {title}
      </Text>
      <View style={styles.spacer} />
    </View>
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
  title: { flex: 1, textAlign: "center", color: colors.text, fontWeight: "700" },
  spacer: { width: 80 },
});
