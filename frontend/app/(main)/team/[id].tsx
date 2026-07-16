import React, { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import { TeamUser, listUsers, lockUser, unlockUser } from "../../../src/api/team";
import { ErrorText } from "../../../src/ui/form";
import { colors, radius, spacing, type } from "../../../src/ui/theme";

function roleLabel(role: TeamUser["role"]): string {
  return role === "ceo" ? "CEO" : role === "manager" ? "Manager" : "Nhân viên";
}

export default function TeamDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [users, setUsers] = useState<TeamUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lockBusy, setLockBusy] = useState(false);

  const load = () => {
    listUsers()
      .then(setUsers)
      .catch((e: any) => setError(String(e?.message ?? e)));
  };

  useEffect(() => {
    load();
  }, []);

  const target = users?.find((u) => u.id === id) ?? null;
  const manager = target?.manager_id ? users?.find((u) => u.id === target.manager_id) : null;

  const toggleLock = () => {
    if (!target) return;
    const locking = target.status === "active";
    Alert.alert(
      locking ? "Khóa tài khoản?" : "Mở khóa tài khoản?",
      locking
        ? `${target.full_name} sẽ bị đăng xuất khỏi mọi thiết bị.`
        : `${target.full_name} sẽ đăng nhập lại được.`,
      [
        { text: "Hủy", style: "cancel" },
        {
          text: locking ? "Khóa" : "Mở khóa",
          style: locking ? "destructive" : "default",
          onPress: async () => {
            setLockBusy(true);
            try {
              await (locking ? lockUser(target.id) : unlockUser(target.id));
              load();
            } catch (e: any) {
              Alert.alert("Không thực hiện được", String(e?.message ?? e));
            } finally {
              setLockBusy(false);
            }
          },
        },
      ],
    );
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
    >
      {users === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {users !== null && !target && <ErrorText error="Không tìm thấy người này" />}
      {target && (
        <>
          <View style={styles.card}>
            <Text style={styles.title}>{target.full_name}</Text>
            <Text style={{ color: colors.textSecondary }}>{target.email}</Text>
            <Text style={{ marginTop: spacing.xs, color: colors.text }}>
              Vai trò: {roleLabel(target.role)}
            </Text>
            {manager && (
              <Text style={{ color: colors.text }}>Báo cáo cho: {manager.full_name}</Text>
            )}
            <Text style={{ color: target.status === "locked" ? colors.danger : colors.success }}>
              {target.status === "locked" ? "Đã khóa" : "Đang hoạt động"}
            </Text>
          </View>
          <View style={styles.card}>
            <Text style={styles.title}>Hành động</Text>
            <TouchableOpacity onPress={toggleLock} disabled={lockBusy}>
              {lockBusy ? (
                <ActivityIndicator color={colors.primary} />
              ) : (
                <Text style={{ color: colors.primary, fontWeight: "700" }}>
                  {target.status === "locked" ? "Mở khóa" : "Khóa tài khoản"}
                </Text>
              )}
            </TouchableOpacity>
          </View>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  title: { ...type.heading },
});
