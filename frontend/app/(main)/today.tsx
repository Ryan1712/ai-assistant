import React, { useCallback, useEffect, useState } from "react";
import { RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { DashTask, TodayDashboard, getTodayDashboard } from "../../src/api/dashboard";

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
});
