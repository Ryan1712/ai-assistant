import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import DateTimePicker from "@react-native-community/datetimepicker";
import { AuditEvent, listAuditEvents } from "../../src/api/audit";
import { BackHeader } from "../../src/ui/BackHeader";
import { ErrorText } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";

const TYPE_ICON: Record<AuditEvent["type"], string> = {
  task_update: "📋",
  login: "🔐",
  instruction_edit: "🧠",
  skill_edit: "🧠",
  account_event: "👤",
};

function fmtDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function AuditEventRow({ e }: { e: AuditEvent }) {
  return (
    <View style={styles.row}>
      <Text style={{ fontSize: 18 }}>{TYPE_ICON[e.type]}</Text>
      <View style={{ flex: 1 }}>
        <Text style={type.body}>{e.summary}</Text>
        <Text style={{ color: colors.textSecondary }}>
          bởi {e.actor_name} · {new Date(e.created_at).toLocaleString("vi-VN")}
          {e.type === "account_event" && e.target_name ? ` → ${e.target_name}` : ""}
        </Text>
      </View>
    </View>
  );
}

export default function AuditLog() {
  const [dateFrom, setDateFrom] = useState<Date | null>(null);
  const [dateTo, setDateTo] = useState<Date | null>(null);
  const [showFromPicker, setShowFromPicker] = useState(false);
  const [showToPicker, setShowToPicker] = useState(false);
  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    setEvents(null);
    listAuditEvents(dateFrom ? fmtDate(dateFrom) : undefined, dateTo ? fmtDate(dateTo) : undefined)
      .then(setEvents)
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, [dateFrom, dateTo]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <BackHeader title="Nhật ký thay đổi" />
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
      >
      <View style={styles.card}>
        <View style={styles.filterRow}>
          <TouchableOpacity onPress={() => setShowFromPicker(true)}>
            <Text style={{ color: colors.primary }}>
              Từ ngày: {dateFrom ? fmtDate(dateFrom) : "Chưa chọn"}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setShowToPicker(true)}>
            <Text style={{ color: colors.primary }}>
              Đến ngày: {dateTo ? fmtDate(dateTo) : "Chưa chọn"}
            </Text>
          </TouchableOpacity>
        </View>
        {(dateFrom || dateTo) && (
          <TouchableOpacity
            onPress={() => {
              setDateFrom(null);
              setDateTo(null);
            }}
          >
            <Text style={{ color: colors.danger, marginTop: spacing.sm }}>Xóa lọc</Text>
          </TouchableOpacity>
        )}
      </View>
      {showFromPicker && (
        <DateTimePicker
          value={dateFrom ?? new Date()}
          mode="date"
          onChange={(event, selectedDate) => {
            setShowFromPicker(false);
            if (event.type === "set" && selectedDate) setDateFrom(selectedDate);
          }}
        />
      )}
      {showToPicker && (
        <DateTimePicker
          value={dateTo ?? new Date()}
          mode="date"
          onChange={(event, selectedDate) => {
            setShowToPicker(false);
            if (event.type === "set" && selectedDate) setDateTo(selectedDate);
          }}
        />
      )}
      {events === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {events?.length === 0 && (
        <Text style={{ color: colors.textMuted }}>
          {dateFrom || dateTo ? "Không có hoạt động nào trong khoảng thời gian này" : "Chưa có hoạt động nào"}
        </Text>
      )}
      {events && events.length > 0 && (
        <View style={styles.card}>
          {events.map((e, i) => (
            <AuditEventRow key={`${e.type}-${e.actor_id}-${e.created_at}-${i}`} e={e} />
          ))}
        </View>
      )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg },
  filterRow: { flexDirection: "row", justifyContent: "space-between" },
  row: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
});
