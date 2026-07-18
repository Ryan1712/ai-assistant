import React, { useEffect, useState } from "react";
import { ActivityIndicator, Alert, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import * as Sharing from "expo-sharing";
import { File, Paths } from "expo-file-system";
import { Report, fetchReportBytes, listReports } from "../../src/api/reports";
import { BackHeader } from "../../src/ui/BackHeader";
import { ErrorText } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";

const KIND_LABEL: Record<string, string> = {
  task_summary: "Tổng hợp task",
};

function ReportRow({ r }: { r: Report }) {
  const [downloading, setDownloading] = useState(false);
  const summary = r.summary as { total?: number };

  const handleDownload = async () => {
    setDownloading(true);
    try {
      const bytes = await fetchReportBytes(r.id);
      const file = new File(Paths.cache, `report-${r.id}.xlsx`);
      file.create({ overwrite: true });
      file.write(new Uint8Array(bytes));
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(file.uri);
      } else {
        Alert.alert("Thiết bị này không hỗ trợ chia sẻ file.");
      }
    } catch (e: any) {
      Alert.alert("Không tải được báo cáo", String(e?.message ?? e));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <TouchableOpacity style={styles.row} onPress={handleDownload} disabled={downloading}>
      <View style={{ flex: 1 }}>
        <Text style={type.body}>{KIND_LABEL[r.kind] ?? r.kind}</Text>
        <Text style={{ color: colors.textSecondary }}>
          {summary.total ?? 0} task — {new Date(r.created_at).toLocaleString("vi-VN")}
        </Text>
      </View>
      {downloading ? (
        <ActivityIndicator color={colors.primary} />
      ) : (
        <Text style={{ color: colors.primary, fontWeight: "700" }}>⬇ Tải</Text>
      )}
    </TouchableOpacity>
  );
}

export default function Reports() {
  const [reports, setReports] = useState<Report[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listReports()
      .then(setReports)
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, []);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <BackHeader title="Báo cáo" />
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
      >
      <Text style={type.caption}>
        Báo cáo tạo qua chat hoặc lịch tự động — bấm để tải file Excel.
      </Text>
      {reports === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {reports?.length === 0 && (
        <Text style={{ color: colors.textMuted }}>
          Chưa có báo cáo nào — nhắn AI để tạo, ví dụ "xuất báo cáo task tháng này"
        </Text>
      )}
      {reports && reports.length > 0 && (
        <View style={styles.card}>
          {reports.map((r) => (
            <ReportRow key={r.id} r={r} />
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
