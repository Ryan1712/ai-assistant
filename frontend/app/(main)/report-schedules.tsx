import React, { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { ReportSchedule, deleteReportSchedule, listReportSchedules } from "../../src/api/reportSchedules";
import { BackHeader } from "../../src/ui/BackHeader";
import { ErrorText } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";

const WEEKDAY_LABEL = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"];

function scheduleLabel(s: ReportSchedule): string {
  const day = s.weekday === null ? "Hàng ngày" : WEEKDAY_LABEL[s.weekday];
  const time = `${String(s.hour).padStart(2, "0")}:${String(s.minute).padStart(2, "0")}`;
  return `${day}, ${time}`;
}

function ScheduleRow({
  s,
  onDeleted,
  onError,
}: {
  s: ReportSchedule;
  onDeleted: (id: string) => void;
  onError: (msg: string) => void;
}) {
  const confirmDelete = () => {
    Alert.alert("Hủy lịch báo cáo?", "Sẽ không còn tự động gửi báo cáo theo lịch này nữa.", [
      { text: "Hủy", style: "cancel" },
      {
        text: "Xóa",
        style: "destructive",
        onPress: async () => {
          try {
            await deleteReportSchedule(s.id);
            onDeleted(s.id);
          } catch (e: any) {
            onError(String(e?.message ?? e));
          }
        },
      },
    ]);
  };

  return (
    <View style={styles.row}>
      <View style={{ flex: 1 }}>
        <Text style={type.heading}>{scheduleLabel(s)}</Text>
        <Text style={{ color: colors.textSecondary }}>
          Kế tiếp: {new Date(s.next_run_at).toLocaleString("vi-VN")}
        </Text>
        {!s.active && <Text style={{ color: colors.textMuted }}>Tạm dừng</Text>}
      </View>
      <TouchableOpacity onPress={confirmDelete}>
        <Text style={{ color: colors.danger, fontWeight: "700" }}>Xóa</Text>
      </TouchableOpacity>
    </View>
  );
}

export default function ReportSchedules() {
  const [schedules, setSchedules] = useState<ReportSchedule[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listReportSchedules()
      .then(setSchedules)
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, []);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <BackHeader title="Báo cáo định kỳ" />
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
      >
      {schedules === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {schedules?.length === 0 && (
        <Text style={{ color: colors.textMuted }}>
          Chưa có lịch báo cáo nào — nhắn AI để đặt lịch, ví dụ &quot;gửi báo cáo mỗi sáng thứ 2 lúc
          8h&quot;
        </Text>
      )}
      {schedules && schedules.length > 0 && (
        <View style={styles.card}>
          {schedules.map((s) => (
            <ScheduleRow
              key={s.id}
              s={s}
              onDeleted={(id) => setSchedules((prev) => (prev ? prev.filter((x) => x.id !== id) : prev))}
              onError={setError}
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
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
});
