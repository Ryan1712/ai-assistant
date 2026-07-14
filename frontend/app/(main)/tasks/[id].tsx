import React, { useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { TaskDetail, getTask } from "../../../src/api/tasks";
import { ErrorText } from "../../../src/ui/form";
import { colors, radius, spacing, type } from "../../../src/ui/theme";

export default function TaskDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const t = await getTask(id);
        if (!cancelled) setTask(t);
      } catch (e: any) {
        if (!cancelled) setError(String(e?.message ?? e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
    >
      {!task && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {task && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>{task.title}</Text>
          <Text style={styles.meta}>
            {task.status} — {task.percent}%
          </Text>
          {task.description !== "" && <Text style={styles.body}>{task.description}</Text>}
          {task.deadline && (
            <Text style={styles.meta}>
              Deadline: {new Date(task.deadline).toLocaleDateString("vi-VN")}
            </Text>
          )}
          <Text style={styles.meta}>Ưu tiên: {task.priority}</Text>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  cardTitle: { ...type.heading },
  meta: { color: colors.textSecondary },
  body: { ...type.body },
});
