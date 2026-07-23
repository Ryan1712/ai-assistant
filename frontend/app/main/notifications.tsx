import React, { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import {
  Notification,
  getNotificationPreferences,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  setNotificationPreference,
} from "../../src/api/notifications";
import { ackDirective, raiseDirectiveQuestion, renegotiateDirective } from "../../src/api/directives";
import { BackHeader } from "../../src/ui/BackHeader";
import { ErrorText, Field } from "../../src/ui/form";
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
  { type: "directive_assigned", label: "Được giao việc chính thức" },
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
    case "directive_assigned": {
      const task = p.task_title ? ` (${p.task_title})` : "";
      return { title: `${p.from_name} giao việc: ${p.summary}${task}` };
    }
    default:
      return { title: n.type };
  }
}

type DirectiveFormMode = "idle" | "question" | "renegotiate";

/** Directive (Phase 3): dòng thông báo duy nhất có nút hành động thay vì chỉ
 * tap-to-navigate — người nhận phản hồi ngay tại đây (Nhận việc / Hỏi lại /
 * Xin dời hạn), không cần mở màn hình khác. */
function DirectiveAssignedRow({
  n,
  onRead,
}: {
  n: Notification;
  onRead: (id: string) => void;
}) {
  const p = n.payload as Record<string, any>;
  const directiveId = p.directive_id as string;
  const [mode, setMode] = useState<DirectiveFormMode>("idle");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [acted, setActed] = useState(false);
  const unread = n.read_at === null;

  const markReadOnce = () => {
    if (unread) {
      markNotificationRead(n.id).catch(() => {});
      onRead(n.id);
    }
  };

  const doAck = async () => {
    setBusy(true);
    setError(null);
    try {
      await ackDirective(directiveId);
      markReadOnce();
      setActed(true);
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const submitForm = async () => {
    if (!text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      if (mode === "question") await raiseDirectiveQuestion(directiveId, text.trim());
      else await renegotiateDirective(directiveId, text.trim());
      markReadOnce();
      setActed(true);
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const { title } = describe(n);

  return (
    <View style={styles.row}>
      {unread && <View style={styles.dot} />}
      <View style={{ flex: 1 }}>
        <Text style={{ ...type.body, fontWeight: unread ? "700" : "400" }}>{title}</Text>
        <Text style={{ color: colors.textSecondary }}>
          {new Date(n.created_at).toLocaleString("vi-VN")}
        </Text>
        {acted ? (
          <Text style={{ color: colors.success, marginTop: spacing.xs, fontWeight: "700" }}>
            ✓ Đã phản hồi
          </Text>
        ) : (
          <>
            <ErrorText error={error} />
            {mode === "idle" && (
              <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm }}>
                <TouchableOpacity style={styles.okBtn} onPress={doAck} disabled={busy}>
                  {busy ? (
                    <ActivityIndicator color={colors.onPrimary} />
                  ) : (
                    <Text style={{ color: colors.onPrimary, fontWeight: "700" }}>Nhận việc</Text>
                  )}
                </TouchableOpacity>
                <TouchableOpacity style={styles.secondaryBtn} onPress={() => setMode("question")}
                                  disabled={busy}>
                  <Text style={{ color: colors.text }}>Hỏi lại</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.secondaryBtn} onPress={() => setMode("renegotiate")}
                                  disabled={busy}>
                  <Text style={{ color: colors.text }}>Xin dời hạn</Text>
                </TouchableOpacity>
              </View>
            )}
            {mode !== "idle" && (
              <View style={{ marginTop: spacing.sm }}>
                <Field
                  placeholder={mode === "question" ? "Câu hỏi của bạn…" : "Lý do xin dời hạn…"}
                  value={text}
                  onChangeText={setText}
                  multiline
                />
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <TouchableOpacity style={styles.okBtn} onPress={submitForm}
                                    disabled={busy || !text.trim()}>
                    {busy ? (
                      <ActivityIndicator color={colors.onPrimary} />
                    ) : (
                      <Text style={{ color: colors.onPrimary, fontWeight: "700" }}>Gửi</Text>
                    )}
                  </TouchableOpacity>
                  <TouchableOpacity style={styles.secondaryBtn}
                                    onPress={() => { setMode("idle"); setText(""); }}
                                    disabled={busy}>
                    <Text style={{ color: colors.text }}>Hủy</Text>
                  </TouchableOpacity>
                </View>
              </View>
            )}
          </>
        )}
      </View>
    </View>
  );
}

function NotificationRow({
  n,
  onRead,
}: {
  n: Notification;
  onRead: (id: string) => void;
}) {
  const navigation = useNavigation<any>();

  if (n.type === "directive_assigned") {
    return <DirectiveAssignedRow n={n} onRead={onRead} />;
  }

  const { title, taskId, goTo } = describe(n);
  const unread = n.read_at === null;

  const handlePress = () => {
    if (unread) {
      markNotificationRead(n.id).catch(() => {});
      onRead(n.id);
    }
    if (taskId) navigation.navigate("TaskDetail", { id: taskId });
    else if (goTo === "emails") navigation.navigate("Emails");
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
  okBtn: {
    backgroundColor: colors.success,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  secondaryBtn: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderWidth: 1,
    borderColor: colors.borderStrong,
  },
});
