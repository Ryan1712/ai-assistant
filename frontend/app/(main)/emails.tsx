import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useRouter } from "expo-router";
import { Email, listEmails } from "../../src/api/emails";
import { BackHeader } from "../../src/ui/BackHeader";
import { ErrorText } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";

type Box = "inbox" | "sent";

function BoxToggle({ box, onChange }: { box: Box; onChange: (b: Box) => void }) {
  return (
    <View style={styles.tabRow}>
      <TouchableOpacity
        style={[styles.chip, box === "inbox" ? styles.chipActive : styles.chipInactive]}
        onPress={() => onChange("inbox")}
      >
        <Text style={box === "inbox" ? styles.chipTextActive : styles.chipTextInactive}>
          Hộp thư đến
        </Text>
      </TouchableOpacity>
      <TouchableOpacity
        style={[styles.chip, box === "sent" ? styles.chipActive : styles.chipInactive]}
        onPress={() => onChange("sent")}
      >
        <Text style={box === "sent" ? styles.chipTextActive : styles.chipTextInactive}>Đã gửi</Text>
      </TouchableOpacity>
    </View>
  );
}

function EmailRow({ email, box }: { email: Email; box: Box }) {
  const router = useRouter();
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>
        {box === "inbox" ? `Từ: ${email.counterpart_name}` : `Đến: ${email.counterpart_name}`}
      </Text>
      <Text style={styles.subject}>{email.subject}</Text>
      <Text style={styles.preview} numberOfLines={2}>
        {email.body}
      </Text>
      <Text style={styles.meta}>{new Date(email.created_at).toLocaleString("vi-VN")}</Text>
      {email.task_id && (
        <TouchableOpacity onPress={() => router.push(`/tasks/${email.task_id}`)}>
          <Text style={{ color: colors.primary, fontWeight: "700" }}>Xem task liên quan →</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

export default function EmailsScreen() {
  const [box, setBox] = useState<Box>("inbox");
  const [emails, setEmails] = useState<Email[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((b: Box) => {
    setError(null);
    setEmails(null);
    listEmails(b)
      .then(setEmails)
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, []);

  useEffect(() => {
    load(box);
  }, [box, load]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <BackHeader title="Email" />
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
      >
      <Text style={styles.caption}>Gửi mail bằng cách nhắn AI trong mục Trợ lý AI.</Text>
      <BoxToggle box={box} onChange={setBox} />
      {emails === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {emails?.length === 0 && (
        <Text style={styles.empty}>
          {box === "inbox" ? "Chưa có mail nào trong hộp thư đến" : "Chưa gửi mail nào"}
        </Text>
      )}
      {emails && emails.length > 0 && (
        <View style={styles.card}>
          {emails.map((e) => (
            <EmailRow key={e.id} email={e} box={box} />
          ))}
        </View>
      )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  caption: { ...type.caption },
  tabRow: { flexDirection: "row", gap: spacing.sm },
  chip: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  chipActive: { borderColor: colors.primary, backgroundColor: colors.surface },
  chipInactive: { borderColor: colors.border, backgroundColor: colors.surface },
  chipTextActive: { color: colors.primary, fontWeight: "700" },
  chipTextInactive: { color: colors.textSecondary, fontWeight: "400" },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg },
  row: {
    gap: spacing.xs,
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
  rowLabel: { ...type.caption },
  subject: { ...type.heading },
  preview: { ...type.body, color: colors.textSecondary },
  meta: { ...type.caption },
  empty: { color: colors.textMuted },
});
