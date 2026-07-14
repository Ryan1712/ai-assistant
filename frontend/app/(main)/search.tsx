import React, { useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useRouter } from "expo-router";
import { SearchResult, SearchTask, searchAll } from "../../src/api/search";
import { ErrorText, Field } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";

function TaskRow({ t }: { t: SearchTask }) {
  const router = useRouter();
  return (
    <TouchableOpacity style={styles.row} onPress={() => router.push(`/tasks/${t.id}`)}>
      <Text style={{ flex: 1 }} numberOfLines={1}>
        {t.title}
      </Text>
      <Text style={styles.status}>{t.status}</Text>
    </TouchableOpacity>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>{title}</Text>
      {children}
    </View>
  );
}

export default function Search() {
  const [q, setQ] = useState("");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runSearch = async () => {
    if (!q.trim()) return;
    setLoading(true);
    setError(null);
    try {
      setResult(await searchAll(q.trim()));
    } catch (e: any) {
      setResult(null);
      setError(String(e?.message ?? e));
    } finally {
      setLoading(false);
    }
  };

  const total = result
    ? result.tasks.length + result.notes.length + result.voice_notes.length +
      result.users.length + result.skills.length
    : 0;

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
    >
      <Field
        placeholder="Tìm task, note, ghi âm, người, skill…"
        value={q}
        onChangeText={setQ}
        onSubmitEditing={runSearch}
        returnKeyType="search"
      />
      {loading && <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />}
      <ErrorText error={error} />
      {!loading && !error && result === null && (
        <Text style={styles.empty}>Nhập từ khóa để tìm task, note, ghi âm, người, skill</Text>
      )}
      {!loading && !error && result !== null && total === 0 && (
        <Text style={styles.empty}>Không tìm thấy kết quả nào cho "{q.trim()}"</Text>
      )}
      {!loading && !error && result !== null && total > 0 && (
        <>
          {result.tasks.length > 0 && (
            <Section title="🗂️ Task">
              {result.tasks.map((t) => (
                <TaskRow key={t.id} t={t} />
              ))}
            </Section>
          )}
          {result.notes.length > 0 && (
            <Section title="📝 Note">
              {result.notes.map((n) => (
                <Text key={n.id} style={styles.plainRow}>
                  {n.content}
                </Text>
              ))}
            </Section>
          )}
          {result.voice_notes.length > 0 && (
            <Section title="🎙️ Ghi âm">
              {result.voice_notes.map((v) => (
                <Text key={v.id} style={styles.plainRow}>
                  {v.transcript}
                </Text>
              ))}
            </Section>
          )}
          {result.users.length > 0 && (
            <Section title="👤 Người">
              {result.users.map((u) => (
                <Text key={u.id} style={styles.plainRow}>
                  {u.full_name} — {u.email}
                </Text>
              ))}
            </Section>
          )}
          {result.skills.length > 0 && (
            <Section title="🧠 Skill">
              {result.skills.map((s) => (
                <Text key={s.id} style={styles.plainRow}>
                  {s.name}
                </Text>
              ))}
            </Section>
          )}
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg },
  cardTitle: { ...type.heading, marginBottom: spacing.sm },
  empty: { color: colors.textMuted },
  row: {
    flexDirection: "row",
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
  status: { color: colors.primary, fontWeight: "700" },
  plainRow: {
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
});
