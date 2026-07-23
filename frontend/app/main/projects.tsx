import React, { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { Project, listProjects } from "../../src/api/projects";
import { TaskDetail, listTasks } from "../../src/api/tasks";
import { BackHeader } from "../../src/ui/BackHeader";
import { ErrorText } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";

const STATUS_LABEL: Record<string, string> = {
  active: "Đang chạy",
  completed: "Hoàn thành",
  on_hold: "Tạm dừng",
};

function ProjectCard({ p, tasks }: { p: Project; tasks: TaskDetail[] }) {
  const navigation = useNavigation<any>();
  const [expanded, setExpanded] = useState(false);
  const done = tasks.filter((t) => t.status === "done").length;
  const percent = tasks.length > 0 ? Math.round((done / tasks.length) * 100) : 0;

  return (
    <View style={styles.card}>
      <TouchableOpacity onPress={() => setExpanded((e) => !e)}>
        <View style={styles.rowHeader}>
          <Text style={styles.cardTitle}>{p.name}</Text>
          <View style={styles.badge}>
            <Text style={styles.badgeText}>{STATUS_LABEL[p.status] ?? p.status}</Text>
          </View>
        </View>
        {p.goal !== "" && <Text style={{ color: colors.textSecondary }}>{p.goal}</Text>}
        <Text style={{ color: colors.textSecondary, marginTop: spacing.xs }}>
          {done}/{tasks.length} task hoàn thành ({percent}%)
          {p.deadline && ` — Hạn: ${new Date(p.deadline).toLocaleDateString("vi-VN")}`}
        </Text>
      </TouchableOpacity>
      {expanded && (
        <View style={{ marginTop: spacing.sm }}>
          {tasks.length === 0 && (
            <Text style={{ color: colors.textMuted }}>Chưa có task trong project này</Text>
          )}
          {tasks.map((t) => (
            <TouchableOpacity
              key={t.id}
              style={styles.taskRow}
              onPress={() => navigation.navigate("TaskDetail", { id: t.id })}
            >
              <Text style={{ flex: 1 }} numberOfLines={1}>
                {t.title}
              </Text>
              <Text style={{ color: colors.textSecondary }}>{t.percent}%</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
    </View>
  );
}

export default function Projects() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [tasks, setTasks] = useState<TaskDetail[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listProjects(), listTasks()])
      .then(([p, t]) => {
        setProjects(p);
        setTasks(t);
      })
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, []);

  const tasksByProject = useMemo(() => {
    const map = new Map<string, TaskDetail[]>();
    tasks?.forEach((t) => {
      const list = map.get(t.project_id) ?? [];
      list.push(t);
      map.set(t.project_id, list);
    });
    return map;
  }, [tasks]);

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg }}>
      <BackHeader title="Project" />
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
      >
      {projects === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {projects?.length === 0 && (
        <Text style={{ color: colors.textMuted }}>Chưa có project nào</Text>
      )}
      {projects?.map((p) => (
        <ProjectCard key={p.id} p={p} tasks={tasksByProject.get(p.id) ?? []} />
      ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg },
  cardTitle: { ...type.heading },
  rowHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  badge: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  badgeText: { color: colors.textSecondary, fontSize: type.caption.fontSize, fontWeight: "700" },
  taskRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
});
