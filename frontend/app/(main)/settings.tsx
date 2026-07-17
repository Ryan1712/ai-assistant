import React, { useEffect, useState } from "react";
import { ActivityIndicator, Alert, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useRouter } from "expo-router";
import { useAuth } from "../../src/auth/AuthContext";
import { Subscription, getInviteCode, getSubscription, switchPlan } from "../../src/api/dashboard";
import { colors, radius, spacing, type } from "../../src/ui/theme";

export default function Settings() {
  const { user, signOut } = useAuth();
  const router = useRouter();
  const [sub, setSub] = useState<Subscription | null>(null);
  const [inviteCode, setInviteCode] = useState<string | null>(null);
  const [planBusy, setPlanBusy] = useState(false);

  const togglePlan = () => {
    if (!sub) return;
    setPlanBusy(true);
    switchPlan(sub.plan === "advanced" ? "basic" : "advanced")
      .then(setSub)
      .catch((e: any) => Alert.alert("Không đổi được gói", String(e?.message ?? e)))
      .finally(() => setPlanBusy(false));
  };

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
          {user?.role === "ceo" && (
            <TouchableOpacity onPress={togglePlan} disabled={planBusy} style={{ marginTop: spacing.sm }}>
              {planBusy ? (
                <ActivityIndicator color={colors.primary} />
              ) : (
                <Text style={{ color: colors.primary, fontWeight: "700" }}>
                  Chuyển sang {sub.plan === "advanced" ? "Basic" : "Advanced"} (mock)
                </Text>
              )}
            </TouchableOpacity>
          )}
        </View>
      )}
      {user?.role === "ceo" && (
        <TouchableOpacity style={styles.card} onPress={() => router.push("/reports")}>
          <Text style={styles.title}>📊 Báo cáo</Text>
          <Text style={{ color: colors.textSecondary }}>Xem và tải các báo cáo đã tạo</Text>
        </TouchableOpacity>
      )}
      {user?.role === "ceo" && sub?.plan === "advanced" && (
        <TouchableOpacity style={styles.card} onPress={() => router.push("/report-schedules")}>
          <Text style={styles.title}>📅 Báo cáo định kỳ</Text>
          <Text style={{ color: colors.textSecondary }}>Xem và hủy lịch gửi báo cáo tự động</Text>
        </TouchableOpacity>
      )}
      {user?.role === "ceo" && sub?.plan === "advanced" && (
        <TouchableOpacity style={styles.card} onPress={() => router.push("/portal")}>
          <Text style={styles.title}>🌐 Báo cáo cổng CEO</Text>
          <Text style={{ color: colors.textSecondary }}>Đọc báo cáo từ ceo.9learning.edu.vn</Text>
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
      {user?.role === "ceo" && (
        <TouchableOpacity style={styles.card} onPress={() => router.push("/instructions")}>
          <Text style={styles.title}>🧭 Chỉ dẫn cho AI</Text>
          <Text style={{ color: colors.textSecondary }}>Quy tắc/bối cảnh AI nạp lại ngay khi đổi</Text>
        </TouchableOpacity>
      )}
      <TouchableOpacity style={styles.card} onPress={() => router.push("/skills")}>
        <Text style={styles.title}>🧩 Skill</Text>
        <Text style={{ color: colors.textSecondary }}>Hồ sơ năng lực & gói tri thức nghiệp vụ</Text>
      </TouchableOpacity>
      <TouchableOpacity style={styles.card} onPress={() => router.push("/notes")}>
        <Text style={styles.title}>📝 Ghi chú</Text>
        <Text style={{ color: colors.textSecondary }}>Ghi chú cá nhân theo ngày/tag</Text>
      </TouchableOpacity>
      <TouchableOpacity style={styles.card} onPress={() => router.push("/emails")}>
        <Text style={styles.title}>✉️ Email</Text>
        <Text style={{ color: colors.textSecondary }}>Xem hộp thư đến/đã gửi</Text>
      </TouchableOpacity>
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
