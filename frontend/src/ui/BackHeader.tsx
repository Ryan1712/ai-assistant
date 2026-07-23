import React from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useNavigation } from "@react-navigation/native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors, fonts, spacing } from "./theme";

/** Header dùng chung cho mọi màn phụ (push từ Cài đặt/màn khác). Các màn này không
 * nằm trong tab bar nên tự render header + nút back. headerShown=false ở stack. */
export function BackHeader({ title }: { title: string }) {
  const navigation = useNavigation<any>();
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.headerBar, { paddingTop: insets.top + spacing.sm }]}>
      <TouchableOpacity
        onPress={() => (navigation.canGoBack() ? navigation.goBack() : navigation.navigate("Drawer"))}
        accessibilityLabel="Quay lại"
        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        style={styles.backBtn}
      >
        <Ionicons name="chevron-back" size={22} color={colors.primary} />
        <Text style={styles.backText}>Quay lại</Text>
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
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.sm,
    borderBottomWidth: 1,
    borderColor: colors.divider,
    backgroundColor: colors.surface,
  },
  backBtn: { flexDirection: "row", alignItems: "center", width: 90 },
  backText: { color: colors.primary, fontFamily: fonts.semibold, fontSize: 16 },
  title: { flex: 1, textAlign: "center", color: colors.text, fontFamily: fonts.bold, fontSize: 17 },
  spacer: { width: 90 },
});
