import React, { useCallback, useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { DrawerContentComponentProps, useDrawerStatus } from "@react-navigation/drawer";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Conversation, createConversation, listConversations } from "../api/chat";
import { useAuth } from "../auth/AuthContext";
import { colors, fonts, radius, spacing, type } from "../ui/theme";

const MENU: { label: string; icon: keyof typeof Ionicons.glyphMap; route: string }[] = [
  { label: "Chat", icon: "chatbubble-ellipses-outline", route: "Chat" },
  { label: "Dashboard", icon: "grid-outline", route: "Today" },
  { label: "Công việc", icon: "checkbox-outline", route: "Tasks" },
  { label: "Cài đặt", icon: "settings-outline", route: "Settings" },
];

export function DrawerContent({ navigation, state }: DrawerContentComponentProps) {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const [convs, setConvs] = useState<Conversation[]>([]);
  const drawerStatus = useDrawerStatus();

  const activeRoute = state.routeNames[state.index];

  const load = useCallback(() => {
    listConversations()
      .then(setConvs)
      .catch(() => {});
  }, []);

  // Nạp lại danh sách gần đây mỗi khi mở drawer.
  useEffect(() => {
    if (drawerStatus === "open") load();
  }, [drawerStatus, load]);

  // openChat: mở 1 conversation cụ thể (có id) hoặc tạo conversation MỚI (không có id).
  // Async vì cần gọi API createConversation trước khi điều hướng — đảm bảo id mới
  // KHÁC với params hiện tại → React Navigation buộc unmount/remount màn Chat → trắng tinh.
  const openChat = async (id?: string) => {
    if (id) {
      // Mở cuộc cũ: điều hướng thẳng với id đó
      navigation.navigate("Chat", { id });
    } else {
      // Tạo cuộc mới: gọi API trước để lấy id thật, rồi mới navigate
      try {
        const conv = await createConversation();
        navigation.navigate("Chat", { id: conv.id });
      } catch {
        // Báo nhẹ nếu không tạo được — không crash, không để drawer kẹt
        navigation.navigate("Chat", { id: undefined });
      }
    }
    navigation.closeDrawer();
  };

  const initial = (user?.email ?? "U").slice(0, 1).toUpperCase();

  return (
    <View style={styles.root}>
      {/* Nhóm menu trên */}
      <View style={{ paddingTop: insets.top + spacing.md, paddingHorizontal: spacing.sm }}>
        <Text style={styles.brand}>Trợ lý AI</Text>

        {/* Nút "Cuộc trò chuyện mới" — nổi bật, đặt trên nhóm menu */}
        <TouchableOpacity
          style={styles.newChatBtn}
          onPress={() => openChat()}
          accessibilityLabel="Cuộc trò chuyện mới"
          accessibilityRole="button"
        >
          <Ionicons name="add" size={20} color={colors.onPrimary} />
          <Text style={styles.newChatBtnLabel}>Cuộc trò chuyện mới</Text>
        </TouchableOpacity>

        {MENU.map((m) => {
          const active = activeRoute === m.route;
          return (
            <TouchableOpacity
              key={m.route}
              style={[styles.menuItem, active && styles.menuItemActive]}
              onPress={() => {
                // MENU "Chat": luôn điều hướng về active conversation (id: undefined).
                // Nếu đang xem cuộc cũ (params {id: X}), {id: undefined} tạo params mới
                // → React Navigation reload về active conv, không kẹt ở X.
                if (m.route === "Chat") {
                  navigation.navigate("Chat", { id: undefined });
                } else {
                  navigation.navigate(m.route);
                }
                navigation.closeDrawer();
              }}
            >
              <Ionicons name={m.icon} size={22} color={active ? colors.primary : colors.text} />
              <Text style={[styles.menuLabel, active && { color: colors.primary }]}>{m.label}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      <View style={styles.divider} />
      <Text style={styles.sectionLabel}>Gần đây</Text>

      {/* List chat recent (cuộn) */}
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ paddingHorizontal: spacing.sm }}>
        {convs.length === 0 ? (
          <Text style={styles.empty}>Chưa có cuộc trò chuyện</Text>
        ) : (
          convs.map((c) => (
            <TouchableOpacity key={c.id} style={styles.recentItem} onPress={() => openChat(c.id)}>
              <Text style={styles.recentText} numberOfLines={1}>
                {c.title || "Cuộc trò chuyện chưa đặt tên"}
              </Text>
            </TouchableOpacity>
          ))
        )}
        <TouchableOpacity
          style={styles.seeAllRow}
          onPress={() => {
            navigation.navigate("Conversations");
            navigation.closeDrawer();
          }}
        >
          <Text style={styles.seeAll}>Xem tất cả →</Text>
        </TouchableOpacity>
      </ScrollView>

      {/* Đáy: user */}
      <View style={[styles.bottomBar, { paddingBottom: insets.bottom + spacing.sm }]}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>{initial}</Text>
        </View>
        <Text style={styles.userName} numberOfLines={1}>
          {user?.email ?? "Tài khoản"}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  brand: { fontFamily: fonts.extrabold, fontSize: 22, color: colors.text, marginBottom: spacing.md, marginLeft: spacing.sm },
  menuItem: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
  },
  menuItemActive: { backgroundColor: colors.surfaceAlt },
  menuLabel: { fontFamily: fonts.semibold, fontSize: 16, color: colors.text },
  divider: { height: 1, backgroundColor: colors.divider, marginVertical: spacing.md, marginHorizontal: spacing.md },
  sectionLabel: {
    fontFamily: fonts.semibold,
    fontSize: 12,
    color: colors.textMuted,
    marginBottom: spacing.xs,
    marginLeft: spacing.lg,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  empty: { color: colors.textMuted, padding: spacing.md },
  recentItem: { paddingVertical: spacing.md, paddingHorizontal: spacing.md, borderRadius: radius.md },
  recentText: { color: colors.text, fontFamily: fonts.regular, fontSize: 15 },
  seeAllRow: { paddingVertical: spacing.md, paddingHorizontal: spacing.md },
  seeAll: { color: colors.primary, fontFamily: fonts.semibold, fontSize: 14 },
  newChatBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    backgroundColor: colors.primary,
    borderRadius: radius.pill,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.md,
    marginHorizontal: spacing.xs,
  },
  newChatBtnLabel: {
    ...type.bodyStrong,
    color: colors.onPrimary,
  },
  bottomBar: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
  },
  avatar: {
    width: 34,
    height: 34,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceAlt,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: { fontFamily: fonts.bold, color: colors.text, fontSize: 14 },
  userName: { flex: 1, color: colors.textSecondary, fontFamily: fonts.medium, fontSize: 13 },
});
