import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from "expo-audio";
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { useRouter } from "expo-router";
import { DashTask, Subscription, TodayDashboard, getSubscription, getTodayDashboard } from "../../src/api/dashboard";
import { VoiceNote, listVoiceNotes, uploadVoiceNote } from "../../src/api/voice";
import { colors, radius, spacing, type } from "../../src/ui/theme";

function localToday(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

function formatDuration(ms: number): string {
  const totalSeconds = Math.floor(ms / 1000);
  const mm = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const ss = String(totalSeconds % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

const VISIBLE_NOTES = 3;

function QuickVoiceCard() {
  const router = useRouter();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder);
  const [notes, setNotes] = useState<VoiceNote[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (savedTimer.current) clearTimeout(savedTimer.current);
  }, []);

  const loadNotes = useCallback(async () => {
    try {
      setNotes(await listVoiceNotes(localToday()));
    } catch {}
  }, []);

  useEffect(() => {
    loadNotes();
  }, [loadNotes]);

  const toggle = async () => {
    setError(null);
    try {
      if (recorderState.isRecording) {
        setBusy(true);
        await recorder.stop();
        if (recorder.uri) {
          await uploadVoiceNote(recorder.uri);
          await loadNotes();
          setSaved(true); // peak-end: lưu xong phải thấy ngay là đã lưu
          if (savedTimer.current) clearTimeout(savedTimer.current);
          savedTimer.current = setTimeout(() => setSaved(false), 2500);
        }
      } else {
        const perm = await AudioModule.requestRecordingPermissionsAsync();
        if (!perm.granted) {
          setError("Chưa được cấp quyền micro — bật trong Cài đặt để ghi âm.");
          return;
        }
        await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
        await recorder.prepareToRecordAsync();
        recorder.record();
      }
    } catch (e) {
      setError("Ghi âm/tải lên thất bại — thử lại nhé.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={styles.card}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
        <Text style={styles.cardTitle}>🎙️ Ghi âm nhanh</Text>
        <TouchableOpacity onPress={() => router.push("/voice-notes")}>
          <Text style={{ color: colors.primary, fontWeight: "700" }}>Thư viện →</Text>
        </TouchableOpacity>
      </View>
      <TouchableOpacity
        style={[styles.recordBtn, recorderState.isRecording && styles.recordBtnActive]}
        onPress={toggle}
        disabled={busy}
      >
        <Text style={{ color: colors.onPrimary, fontWeight: "700" }}>
          {busy
            ? "Đang tải lên…"
            : recorderState.isRecording
              ? `⏹ Dừng & lưu (${formatDuration(recorderState.durationMillis)})`
              : "🎙️ Ghi âm nhanh"}
        </Text>
      </TouchableOpacity>
      {error && <Text style={styles.error}>{error}</Text>}
      {saved && <Text style={styles.saved}>✓ Đã lưu ghi âm</Text>}
      {notes.length === 0 ? (
        <Text style={styles.empty}>Chưa có ghi âm hôm nay</Text>
      ) : (
        <>
          {notes.slice(0, VISIBLE_NOTES).map((n) => (
            <View key={n.id} style={styles.updateLine}>
              <Text style={{ fontWeight: "600" }}>
                {new Date(n.created_at).toLocaleTimeString("vi-VN", {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
                {n.tags.length > 0 ? ` — ${n.tags.join(", ")}` : ""}
              </Text>
              <Text>{n.transcript || "(chưa có transcript)"}</Text>
            </View>
          ))}
          {notes.length > VISIBLE_NOTES && (
            <TouchableOpacity onPress={() => router.push("/voice-notes")}>
              <Text style={{ color: colors.primary, fontWeight: "700", marginTop: spacing.xs }}>
                +{notes.length - VISIBLE_NOTES} ghi âm khác — xem Thư viện →
              </Text>
            </TouchableOpacity>
          )}
        </>
      )}
    </View>
  );
}

function TaskLine({ t }: { t: DashTask }) {
  const router = useRouter();
  return (
    <TouchableOpacity style={styles.taskLine} onPress={() => router.push(`/tasks/${t.id}`)}>
      <Text style={{ flex: 1 }} numberOfLines={1}>
        {t.title}
      </Text>
      <Text style={styles.percent}>{t.percent}%</Text>
    </TouchableOpacity>
  );
}

function Section({ title, tasks, empty }: { title: string; tasks: DashTask[]; empty: string }) {
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>{title}</Text>
      {tasks.length === 0 ? (
        <Text style={styles.empty}>{empty}</Text>
      ) : (
        tasks.map((t) => <TaskLine key={t.id} t={t} />)
      )}
    </View>
  );
}

export default function Today() {
  const router = useRouter();
  const [data, setData] = useState<TodayDashboard | null>(null);
  const [sub, setSub] = useState<Subscription | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      setData(await getTodayDashboard());
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
    getSubscription().then(setSub).catch(() => {});
  }, [load]);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} />}
    >
      {!data && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      {data && (
        <>
          <TouchableOpacity onPress={() => router.push("/notifications")} style={{ alignSelf: "flex-end" }}>
            <Text style={{ color: colors.primary, fontWeight: "700" }}>🔔 Thông báo</Text>
          </TouchableOpacity>
          <View style={styles.counters}>
            <View style={styles.counter}>
              <Text style={styles.counterNum}>{data.counters.overdue}</Text>
              <Text style={styles.counterLabel}>Trễ hạn</Text>
            </View>
            <View style={styles.counter}>
              <Text style={styles.counterNum}>{data.counters.waiting_on_me}</Text>
              <Text style={styles.counterLabel}>Chờ mình</Text>
            </View>
            <View style={styles.counter}>
              <Text style={styles.counterNum}>{data.counters.updates_24h}</Text>
              <Text style={styles.counterLabel}>Cập nhật 24h</Text>
            </View>
          </View>
          <QuickVoiceCard />
          <Section title="🔥 Quá hạn" tasks={data.overdue} empty="Không có task quá hạn" />
          <Section title="📅 Đến hạn hôm nay" tasks={data.due_today} empty="Hôm nay không có deadline" />
          <Section title="🏃 Đang làm" tasks={data.in_progress} empty="Chưa có task đang chạy" />
          {sub?.plan === "basic" && (
            <Text style={{ color: colors.textMuted, fontStyle: "italic" }}>
              Nâng cấp gói Advanced để xem đầy đủ "Đang làm" và "Cập nhật mới từ đội".
            </Text>
          )}
          <View style={styles.card}>
            <Text style={styles.cardTitle}>🔄 Cập nhật mới từ đội (24h)</Text>
            {data.recent_updates.length === 0 ? (
              <Text style={styles.empty}>
                {sub?.plan === "basic" ? "Chỉ hiện ở gói Advanced" : "Chưa có cập nhật mới"}
              </Text>
            ) : (
              data.recent_updates.map((u, i) => (
                <TouchableOpacity
                  key={i}
                  style={styles.updateLine}
                  onPress={() => router.push(`/tasks/${u.task_id}`)}
                >
                  <Text style={{ fontWeight: "600" }}>
                    {u.author} — {u.task_title}
                    {u.percent != null ? ` (${u.percent}%)` : ""}
                  </Text>
                  <Text>{u.content}</Text>
                </TouchableOpacity>
              ))
            )}
          </View>
          <View style={styles.card}>
            <View style={styles.cardHeaderRow}>
              <Text style={styles.cardTitle}>📝 Ghi chú hôm nay</Text>
              <TouchableOpacity onPress={() => router.push("/notes")}>
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Xem tất cả</Text>
              </TouchableOpacity>
            </View>
            {data.notes_today.length === 0 ? (
              <Text style={styles.empty}>Chưa có ghi chú — nhắn AI “tạo note …”</Text>
            ) : (
              data.notes_today.map((n) => <Text key={n.id}>• {n.content}</Text>)
            )}
          </View>
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  counters: { flexDirection: "row", gap: spacing.md },
  counter: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md,
    alignItems: "center",
  },
  counterNum: { ...type.metric },
  counterLabel: { ...type.caption },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg },
  cardTitle: { ...type.heading, marginBottom: spacing.sm },
  cardHeaderRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  empty: { color: colors.textMuted },
  taskLine: {
    flexDirection: "row",
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
  percent: { color: colors.primary, fontWeight: "700" },
  updateLine: { paddingVertical: spacing.sm, borderTopWidth: 1, borderColor: colors.divider },
  recordBtn: {
    backgroundColor: colors.primary,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    alignItems: "center",
    marginBottom: spacing.sm,
  },
  recordBtnActive: { backgroundColor: colors.danger },
  error: { color: colors.danger, marginBottom: spacing.sm },
  saved: { color: colors.success, fontWeight: "700", marginBottom: spacing.sm },
});
