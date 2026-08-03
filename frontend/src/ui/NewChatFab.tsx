/**
 * NewChatFab — nút nổi (FAB) "Cuộc trò chuyện mới".
 * Vị trí cố định góc phải-dưới, tôn trọng safe-area insets.
 * Render một lần duy nhất ở tầng navigator — KHÔNG nhét vào từng screen.
 * Màu / spacing / bo góc từ theme.ts — KHÔNG inline hex hay số lẻ.
 */
import React from "react";
import { Pressable, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, radius, shadow, spacing } from "./theme";

interface Props {
  onPress: () => void;
}

const FAB_SIZE = 56;

export function NewChatFab({ onPress }: Props) {
  const insets = useSafeAreaInsets();

  return (
    <Pressable
      onPress={onPress}
      accessibilityLabel="Cuộc trò chuyện mới"
      accessibilityRole="button"
      hitSlop={{ top: spacing.sm, bottom: spacing.sm, left: spacing.sm, right: spacing.sm }}
      style={({ pressed }) => [
        styles.fab,
        {
          bottom: insets.bottom + spacing.xl,
          right: insets.right + spacing.xl,
        },
        pressed && styles.pressed,
      ]}
    >
      <Ionicons name="add" size={28} color={colors.onPrimary} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  fab: {
    position: "absolute",
    width: FAB_SIZE,
    height: FAB_SIZE,
    borderRadius: radius.pill,
    backgroundColor: colors.primary,
    alignItems: "center",
    justifyContent: "center",
    ...shadow.card,
  },
  pressed: {
    backgroundColor: colors.primaryPressed,
  },
});
