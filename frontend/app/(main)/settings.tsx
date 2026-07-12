import React, { useEffect, useState } from "react";
import { StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useAuth } from "../../src/auth/AuthContext";
import { Subscription, getInviteCode, getSubscription } from "../../src/api/dashboard";

export default function Settings() {
  const { user, signOut } = useAuth();
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
    <View style={{ flex: 1, padding: 16, gap: 12, backgroundColor: "#f9fafb" }}>
      <View style={styles.card}>
        <Text style={styles.title}>{user?.full_name}</Text>
        <Text style={{ color: "#6b7280" }}>{user?.email}</Text>
        <Text style={{ marginTop: 4 }}>
          Vai trò: {user?.role === "ceo" ? "CEO" : user?.role === "manager" ? "Manager" : "Nhân viên"}
          {user?.is_root ? " (gốc)" : ""}
        </Text>
      </View>
      {sub && (
        <View style={styles.card}>
          <Text style={styles.title}>Gói dịch vụ</Text>
          <Text>{sub.plan === "advanced" ? "Advanced" : "Basic"}</Text>
          {sub.limits && (
            <Text style={{ color: "#6b7280", marginTop: 4 }}>
              Giới hạn: {sub.limits.projects} project · {sub.limits.skills} skill ·{" "}
              {sub.limits.members} thành viên
            </Text>
          )}
        </View>
      )}
      {inviteCode && (
        <View style={styles.card}>
          <Text style={styles.title}>Mã mời công ty</Text>
          <Text selectable style={styles.code}>
            {inviteCode}
          </Text>
          <Text style={{ color: "#6b7280" }}>
            Gửi mã này cho nhân viên để họ tự đăng ký vào công ty.
          </Text>
        </View>
      )}
      <TouchableOpacity style={styles.logout} onPress={signOut}>
        <Text style={{ color: "#dc2626", fontWeight: "600" }}>Đăng xuất</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: "#fff", borderRadius: 12, padding: 14 },
  title: { fontWeight: "700", marginBottom: 4, fontSize: 15 },
  code: { fontSize: 24, fontWeight: "700", letterSpacing: 3, marginVertical: 6 },
  logout: { alignItems: "center", padding: 14 },
});
