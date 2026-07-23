import React, { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { PortalReport, listPortalReports } from "../../src/api/portal";
import { BackHeader } from "../../src/ui/BackHeader";
import { ErrorText } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";

function ReportRow({
  report,
  expanded,
  onToggle,
}: {
  report: PortalReport;
  expanded: boolean;
  onToggle: (id: string) => void;
}) {
  return (
    <TouchableOpacity style={styles.row} onPress={() => onToggle(report.id)}>
      <Text style={type.heading}>{report.title}</Text>
      <Text style={{ color: colors.textSecondary }}>{report.period}</Text>
      <Text style={styles.summary}>{report.summary}</Text>
      {expanded && (
        <View style={styles.dataBox}>
          {Object.entries(report.data).map(([k, v]) => (
            <Text key={k} style={styles.dataLine}>
              {k}: {String(v)}
            </Text>
          ))}
        </View>
      )}
    </TouchableOpacity>
  );
}

export default function PortalScreen() {
  const [reports, setReports] = useState<PortalReport[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [planBlocked, setPlanBlocked] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    listPortalReports()
      .then(setReports)
      .catch((e: any) => {
        // 403 advanced_plan_required là kỳ vọng, không phải lỗi thật — hiển thị
        // thông báo thân thiện thay vì ErrorText. Các lỗi khác dùng ErrorText chuẩn.
        if (e?.status === 403 && e?.detail === "advanced_plan_required") {
          setPlanBlocked(true);
        } else {
          setError(String(e?.message ?? e));
        }
      });
  }, []);

  const toggle = (id: string) => setExpandedId((prev) => (prev === id ? null : id));

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <BackHeader title="Báo cáo cổng CEO" />
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
      >
      <Text style={type.caption}>Báo cáo từ cổng CEO — chỉ đọc.</Text>
      {reports === null && !error && !planBlocked && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      {planBlocked && (
        <View style={styles.card}>
          <Text style={{ color: colors.textMuted }}>Tính năng này chỉ dành cho gói Advanced.</Text>
        </View>
      )}
      <ErrorText error={error} />
      {reports?.length === 0 && <Text style={{ color: colors.textMuted }}>Chưa có báo cáo nào</Text>}
      {reports && reports.length > 0 && (
        <View style={styles.card}>
          {reports.map((r) => (
            <ReportRow key={r.id} report={r} expanded={expandedId === r.id} onToggle={toggle} />
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
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
    gap: spacing.xs,
  },
  summary: { ...type.body },
  dataBox: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.md,
    padding: spacing.md,
    marginTop: spacing.xs,
    gap: spacing.xs,
  },
  dataLine: { color: colors.text, fontSize: type.caption.fontSize },
});
