import React from "react";
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  TouchableOpacity,
} from "react-native";
import { colors, radius, spacing, type } from "./theme";

export function Field({ style, ...props }: TextInputProps) {
  // Merge style của caller LÊN TRÊN styles.field (trước đây {...props} ghi đè làm mất
  // border/padding khi caller truyền style — vd ô tìm kiếm bị mất viền).
  return (
    <TextInput
      placeholderTextColor={colors.textMuted}
      autoCapitalize="none"
      style={[styles.field, style]}
      {...props}
    />
  );
}

export function PrimaryButton({
  title,
  onPress,
  busy,
}: {
  title: string;
  onPress: () => void;
  busy?: boolean;
}) {
  return (
    <TouchableOpacity style={styles.button} onPress={onPress} disabled={busy}>
      {busy ? (
        <ActivityIndicator color={colors.onPrimary} />
      ) : (
        <Text style={styles.buttonText}>{title}</Text>
      )}
    </TouchableOpacity>
  );
}

export function ErrorText({ error }: { error: string | null }) {
  if (!error) return null;
  return <Text style={styles.error}>{error}</Text>;
}

const styles = StyleSheet.create({
  field: {
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    marginBottom: spacing.md,
    fontSize: type.body.fontSize,
    color: colors.text,
    backgroundColor: colors.surface,
  },
  button: {
    backgroundColor: colors.primary,
    borderRadius: radius.md,
    paddingVertical: spacing.lg,
    alignItems: "center",
    marginTop: spacing.xs,
  },
  buttonText: { color: colors.onPrimary, fontSize: type.body.fontSize, fontWeight: "700" },
  error: { color: colors.danger, marginBottom: spacing.sm },
});
