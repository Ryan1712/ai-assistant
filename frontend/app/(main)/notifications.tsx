import React, { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useRouter } from "expo-router";
import {
  Notification,
  getNotificationPreferences,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  setNotificationPreference,
} from "../../src/api/notifications";
import { BackHeader } from "../../src/ui/BackHeader";
import { ErrorText } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";

const NOTIFICATION_TYPES: { type: string; label: string }[] = [
  { type: "task_assigned", label: "Được giao task mới" },
  { type: "task_update", label: "Cập nhật tiến độ task" },
  { type: "account_locked", label: "Tài khoản bị khóa" },
  { type: "role_changed", label: "Đổi vai trò" },
  { type: "offboard_handoff", label: "Bàn giao khi có người nghỉ việc" },
  { type: "management_handoff", label: "Bàn giao khi đổi quản lý" },
  { type: "unlock_request", label: "Yêu cầu mở khóa tài khoản" },
  { type: "scheduled_report", label: "Báo cáo định kỳ sẵn sàng" },
  { type: "email_received", label: "Có mail mới" },
  { type: "mentioned", label: "Được nhắc tên trong bình luận/cập nhật" },
];

function PreferencesSection() {
  const [open, setOpen] = useState(false);
  const [prefs, setPrefs] = useState<Record<string, boolean> | null>(null);
  const [busyType, setBusyType] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const toggleOpen = () => {
    setOpen((o) => !o);
    if (!prefs) {
      getNotificationPreferences()
        .then(setPrefs)
        .catch((e: any) => setError(String(e?.message ?? e)));
    }
  };

  const toggle = async (type: string, currentlyEnabled: boolean) => {
    setBusyType(type);
    setError(null);
    try {
      const updated = await setNotificationPreference(type, !currentlyEnabled);
      setPrefs((prev) => ({ ...prev, ...updated }));
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setBusyType(null);
    }
  };

  return (
    <View style={styles.card}>
      <TouchableOpacity onPress={toggleOpen}>
        <Text style={{ color: colors.primary, fontWeight: "700" }}>
          {open ? "Đóng cài đặt" : "⚙️ Cài đặt loại thông báo"}
        </Text>
      </TouchableOpacity>
      {open && (
        <View style={{ marginTop: spacing.sm }}>
          {prefs === null && !error && <ActivityIndicator color={colors.primary} />}
          <ErrorText error={error} />
          {prefs &&
            NOTIFICATION_TYPES.map(({ type: t, label }) => {
              const enabled = prefs[t] ?? true;
              return (
                <View key={t} style={styles.prefRow}>
                  <Text style={{ flex: 1, ...type.body }}>{label}</Text>
                  <TouchableOpacity onPress={() => toggle(t, enabled)} disabled={busyType === t}>
                    {busyType === t ? (
                      <ActivityIndicator color={colors.primary} />
                    ) : (
                      <Text style={{ color: enabled ? colors.success : colors.textMuted, fontWeight: "700" }}>
                        {enabled ? "Bật" : "Tắt"}
                      </Text>
                    )}
                  </TouchableOpacity>
                </View>
              );
            })}
        </View>
      )}
    </View>
  );
}

function describe(n: Notification): { title: string; taskId?: string; goTo?: "emails" } {
  const p = n.payload as Record<string, any>;
  switch (n.type) {
    case "task_assigned":
      return { title: `Bạn được giao task "${p.title}"`, taskId: p.task_id };
    case "task_update":
      return { title: "Có cập nhật tiến độ mới trên một task bạn theo dõi", taskId: p.task_id };
    case "task_due_soon":
      return { title: `Task "${p.title}" sắp đến hạn`, taskId: p.task_id };
    case "account_locked":
      return { title: "Tài khoản của bạn đã bị khóa" };
    case "role_changed":
      return { title: `Vai trò của bạn đã đổi thành ${p.role}` };
    case "offboard_handoff":
      return {
        title: `Bạn nhận bàn giao ${p.tasks_reassigned} task, ${p.projects_reassigned} project do nghỉ việc`,
      };
    case "management_handoff":
      return {
        title: `Bạn nhận bàn giao ${p.reports_reassigned} nhân sự báo cáo trực tiếp`,
      };
    case "unlock_request":
      return { title: `${p.email} yêu cầu mở khóa tài khoản` };
    case "scheduled_report":
      return { title: `Báo cáo định kỳ đã sẵn sàng: ${p.summary ?? ""}` };
    case "email_received":
      return { title: `${p.from_name} vừa gửi mail: "${p.subject}"`, goTo: "emails" };
    case "mentioned":
      return { title: `${p.from_name} đã nhắc đến bạn trong task "${p.task_title}"`, taskId: p.task_id };
    default:
      return { title: n.type };
  }
}

function NotificationRow({
  n,
  onRead,
}: {
  n: Notification;
  onRead: (id: string) => void;
}) {
  const router = useRouter();
  const { title, taskId, goTo } = describe(n);
  const unread = n.read_at === null;

  const handlePress = () => {
    if (unread) {
      markNotificationRead(n.id).catch(() => {});
      onRead(n.id);
    }
    if (taskId) router.push(`/tasks/${taskId}`);
    else if (goTo === "emails") router.push("/emails");
  };

  return (
    <TouchableOpacity style={styles.row} onPress={handlePress}>
      {unread && <View style={styles.dot} />}
      <View style={{ flex: 1 }}>
        <Text style={{ ...type.body, fontWeight: unread ? "700" : "400" }}>{title}</Text>
        <Text style={{ color: colors.textSecondary }}>
          {new Date(n.created_at).toLocaleString("vi-VN")}
        </Text>
      </View>
    </TouchableOpacity>
  );
}

export default function Notifications() {
  const [notifications, setNotifications] = useState<Notification[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listNotifications()
      .then(setNotifications)
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, []);

  const unreadCount = notifications?.filter((n) => n.read_at === null).length ?? 0;

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setNotifications((prev) =>
        prev ? prev.map((n) => ({ ...n, read_at: n.read_at ?? new Date().toISOString() })) : prev,
      );
    } catch (e: any) {
      setError(String(e?.message ?? e));
    }
  };

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <BackHeader title="Thông báo" />
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
      >
      <PreferencesSection />
      {unreadCount > 0 && (
        <TouchableOpacity onPress={handleMarkAllRead} style={{ alignSelf: "flex-end" }}>
          <Text style={{ color: colors.primary, fontWeight: "700" }}>
            Đánh dấu đã đọc tất cả ({unreadCount})
          </Text>
        </TouchableOpacity>
      )}
      {notifications === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {notifications?.length === 0 && (
        <Text style={{ color: colors.textMuted }}>Chưa có thông báo nào</Text>
      )}
      {notifications && notifications.length > 0 && (
        <View style={styles.card}>
          {notifications.map((n) => (
            <NotificationRow
              key={n.id}
              n={n}
              onRead={(id) =>
                setNotifications((prev) =>
                  prev
                    ? prev.map((x) =>
                        x.id === id ? { ...x, read_at: new Date().toISOString() } : x,
                      )
                    : prev,
                )
              }
            />
          ))}
        </View>
      )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.primary },
  prefRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
});
