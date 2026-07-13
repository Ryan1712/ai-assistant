import {
  AudioModule,
  RecordingPresets,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
} from "expo-audio";
import React, { useCallback, useEffect, useState } from "react";
import {
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { DashTask, TodayDashboard, getTodayDashboard } from "../../src/api/dashboard";
import { VoiceNote, listVoiceNotes, uploadVoiceNote } from "../../src/api/voice";

function localToday(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

function QuickVoiceCard() {
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const recorderState = useAudioRecorderState(recorder);
  const [notes, setNotes] = useState<VoiceNote[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      <Text style={styles.cardTitle}>🎙️ Ghi âm nhanh</Text>
      <TouchableOpacity
        style={[styles.recordBtn, recorderState.isRecording && styles.recordBtnActive]}
        onPress={toggle}
        disabled={busy}
      >
        <Text style={{ color: "#fff", fontWeight: "700" }}>
          {busy
            ? "Đang tải lên…"
            : recorderState.isRecording
              ? "⏹ Dừng & lưu"
              : "🎙️ Ghi âm nhanh"}
        </Text>
      </TouchableOpacity>
      {error && <Text style={styles.error}>{error}</Text>}
      {notes.length === 0 ? (
        <Text style={styles.empty}>Chưa có ghi âm hôm nay</Text>
      ) : (
        notes.map((n) => (
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
        ))
      )}
    </View>
  );
}

function TaskLine({ t }: { t: DashTask }) {
  return (
    <View style={styles.taskLine}>
      <Text style={{ flex: 1 }} numberOfLines={1}>
        {t.title}
      </Text>
      <Text style={styles.percent}>{t.percent}%</Text>
    </View>
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
  const [data, setData] = useState<TodayDashboard | null>(null);
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
  }, [load]);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: "#f9fafb" }}
      contentContainerStyle={{ padding: 12, gap: 12 }}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} />}
    >
      {data && (
        <>
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
          <View style={styles.card}>
            <Text style={styles.cardTitle}>🔄 Cập nhật mới từ đội (24h)</Text>
            {data.recent_updates.length === 0 ? (
              <Text style={styles.empty}>Chưa có cập nhật mới</Text>
            ) : (
              data.recent_updates.map((u, i) => (
                <View key={i} style={styles.updateLine}>
                  <Text style={{ fontWeight: "600" }}>
                    {u.author} — {u.task_title}
                    {u.percent != null ? ` (${u.percent}%)` : ""}
                  </Text>
                  <Text>{u.content}</Text>
                </View>
              ))
            )}
          </View>
          <View style={styles.card}>
            <Text style={styles.cardTitle}>📝 Ghi chú hôm nay</Text>
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
  counters: { flexDirection: "row", gap: 12 },
  counter: {
    flex: 1,
    backgroundColor: "#fff",
    borderRadius: 12,
    padding: 12,
    alignItems: "center",
  },
  counterNum: { fontSize: 24, fontWeight: "700" },
  counterLabel: { color: "#6b7280", fontSize: 12 },
  card: { backgroundColor: "#fff", borderRadius: 12, padding: 14 },
  cardTitle: { fontWeight: "700", marginBottom: 8, fontSize: 15 },
  empty: { color: "#9ca3af" },
  taskLine: { flexDirection: "row", paddingVertical: 6, borderTopWidth: 1, borderColor: "#f3f4f6" },
  percent: { color: "#2563eb", fontWeight: "600" },
  updateLine: { paddingVertical: 6, borderTopWidth: 1, borderColor: "#f3f4f6" },
  recordBtn: {
    backgroundColor: "#2563eb",
    borderRadius: 10,
    paddingVertical: 10,
    alignItems: "center",
    marginBottom: 8,
  },
  recordBtnActive: { backgroundColor: "#dc2626" },
  error: { color: "#dc2626", marginBottom: 8 },
});
