import React, { useEffect, useState } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useRouter } from "expo-router";
import { useAuth } from "../../src/auth/AuthContext";
import { Subscription, getInviteCode, getSubscription } from "../../src/api/dashboard";
import { colors, radius, spacing, type } from "../../src/ui/theme";

export default function Settings() {
  const { user, signOut } = useAuth();
  const router = useRouter();
  const [sub, setSub] = useState<Subscription | null>(null);
  const [inviteCode, setInviteCode] = useState<string | null>(null);

  useEffect(() => {
    getSubscription().then(setSub).catch(() => {});
    if (user?.role === "ceo") {
      getInviteCode()
        .then((r) => setInviteCode(r.invite_code))
        .catch(() => {});
    }
  }, [user]);

  return (
    <View style={{ flex: 1, padding: spacing.lg, gap: spacing.md, backgroundColor: colors.bg }}>
      <View style={styles.card}>
        <Text style={styles.title}>{user?.full_name}</Text>
        <Text style={{ color: colors.textSecondary }}>{user?.email}</Text>
        <Text style={{ marginTop: spacing.xs, color: colors.text }}>
          Vai trò: {user?.role === "ceo" ? "CEO" : user?.role === "manager" ? "Manager" : "Nhân viên"}
          {user?.is_root ? " (gốc)" : ""}
        </Text>
      </View>
      {sub && (
        <View style={styles.card}>
          <Text style={styles.title}>Gói dịch vụ</Text>
          <Text style={{ color: colors.text }}>{sub.plan === "advanced" ? "Advanced" : "Basic"}</Text>
          {sub.limits && (
            <Text style={{ color: colors.textSecondary, marginTop: spacing.xs }}>
              Giới hạn: {sub.limits.projects} project · {sub.limits.skills} skill ·{" "}
              {sub.limits.members} thành viên
            </Text>
          )}
        </View>
      )}
      {user?.role === "ceo" && sub?.plan === "advanced" && (
        <TouchableOpacity style={styles.card} onPress={() => router.push("/report-schedules")}>
          <Text style={styles.title}>📅 Báo cáo định kỳ</Text>
          <Text style={{ color: colors.textSecondary }}>Xem và hủy lịch gửi báo cáo tự động</Text>
        </TouchableOpacity>
      )}
      {user?.role === "ceo" && (
        <TouchableOpacity style={styles.card} onPress={() => router.push("/audit-log")}>
          <Text style={styles.title}>📜 Nhật ký thay đổi</Text>
          <Text style={{ color: colors.textSecondary }}>Xem lịch sử hoạt động của công ty</Text>
        </TouchableOpacity>
      )}
      {user?.role === "ceo" && (
        <TouchableOpacity style={styles.card} onPress={() => router.push("/team")}>
          <Text style={styles.title}>👥 Team</Text>
          <Text style={{ color: colors.textSecondary }}>Quản lý nhân sự: khóa/mở, nghỉ việc, đổi vai trò</Text>
        </TouchableOpacity>
      )}
      {inviteCode && (
        <View style={styles.card}>
          <Text style={styles.title}>Mã mời công ty</Text>
          <Text selectable style={styles.code}>
            {inviteCode}
          </Text>
          <Text style={{ color: colors.textSecondary }}>
            Gửi mã này cho nhân viên để họ tự đăng ký vào công ty.
          </Text>
        </View>
      )}
      <TouchableOpacity style={styles.logout} onPress={signOut}>
        <Text style={{ color: colors.danger, fontWeight: "700" }}>Đăng xuất</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg },
  title: { ...type.heading, marginBottom: spacing.xs },
  code: { ...type.metric, letterSpacing: 3, marginVertical: spacing.sm },
  logout: { alignItems: "center", padding: spacing.lg },
});
