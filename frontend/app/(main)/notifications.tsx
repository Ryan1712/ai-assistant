import React, { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useRouter } from "expo-router";
import {
  Notification,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "../../src/api/notifications";
import { ErrorText } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";

function describe(n: Notification): { title: string; taskId?: string } {
  const p = n.payload as Record<string, any>;
  switch (n.type) {
    case "task_assigned":
      return { title: `Bạn được giao task "${p.title}"`, taskId: p.task_id };
    case "task_update":
      return { title: "Có cập nhật tiến độ mới trên một task bạn theo dõi", taskId: p.task_id };
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
  const { title, taskId } = describe(n);
  const unread = n.read_at === null;

  const handlePress = () => {
    if (unread) {
      markNotificationRead(n.id).catch(() => {});
      onRead(n.id);
    }
    if (taskId) router.push(`/tasks/${taskId}`);
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
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
    >
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
});
