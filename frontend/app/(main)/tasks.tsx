import React, { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useRouter } from "expo-router";
import { useAuth } from "../../src/auth/AuthContext";
import { Project, listProjects } from "../../src/api/projects";
import { TaskDetail, listTasks } from "../../src/api/tasks";
import { TeamUser, listUsers } from "../../src/api/team";
import { ErrorText } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";

const STATUS_LABEL: Record<string, string> = {
  todo: "Chưa bắt đầu",
  in_progress: "Đang làm",
  blocked: "Bị chặn",
  done: "Hoàn thành",
};

const PRIORITY_LABEL: Record<string, string> = {
  low: "Thấp",
  medium: "Trung bình",
  high: "Cao",
};

type FilterKey = "all" | "mine" | "managed" | "overdue" | "blocked" | "done";

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "Tất cả" },
  { key: "mine", label: "Của tôi" },
  { key: "managed", label: "Tôi quản lý" },
  { key: "overdue", label: "Quá hạn" },
  { key: "blocked", label: "Bị chặn" },
  { key: "done", label: "Đã hoàn thành" },
];

function isOverdue(t: TaskDetail): boolean {
  return !!t.deadline && t.status !== "done" && new Date(t.deadline).getTime() < Date.now();
}

function TaskRow({
  t,
  projectName,
  assigneeNames,
}: {
  t: TaskDetail;
  projectName: string;
  assigneeNames: string;
}) {
  const router = useRouter();
  const overdue = isOverdue(t);
  return (
    <TouchableOpacity style={styles.row} onPress={() => router.push(`/tasks/${t.id}`)}>
      <View style={{ flex: 1 }}>
        <Text style={type.body} numberOfLines={1}>
          {t.title}
        </Text>
        <Text style={{ color: colors.textSecondary }} numberOfLines={1}>
          {projectName} — {assigneeNames || "Chưa giao"}
        </Text>
        <Text style={{ color: colors.textSecondary }}>
          {STATUS_LABEL[t.status] ?? t.status} — {t.percent}% — Ưu tiên:{" "}
          {PRIORITY_LABEL[t.priority] ?? t.priority}
          {t.deadline && (
            <Text style={{ color: overdue ? colors.danger : colors.textSecondary }}>
              {" "}
              — Hạn: {new Date(t.deadline).toLocaleDateString("vi-VN")}
            </Text>
          )}
        </Text>
      </View>
    </TouchableOpacity>
  );
}

export default function Tasks() {
  const { user } = useAuth();
  const router = useRouter();
  const [tasks, setTasks] = useState<TaskDetail[] | null>(null);
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [users, setUsers] = useState<TeamUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterKey>("all");

  useEffect(() => {
    Promise.all([listTasks(), listProjects(), listUsers()])
      .then(([t, p, u]) => {
        setTasks(t);
        setProjects(p);
        setUsers(u);
      })
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, []);

  const projectNameById = useMemo(() => {
    const map = new Map<string, string>();
    projects?.forEach((p) => map.set(p.id, p.name));
    return map;
  }, [projects]);

  const userNameById = useMemo(() => {
    const map = new Map<string, string>();
    users?.forEach((u) => map.set(u.id, u.full_name));
    return map;
  }, [users]);

  const managedUserIds = useMemo(() => {
    if (!user) return new Set<string>();
    return new Set((users ?? []).filter((u) => u.manager_id === user.id).map((u) => u.id));
  }, [users, user]);

  const filtered = useMemo(() => {
    if (!tasks) return null;
    switch (filter) {
      case "mine":
        return tasks.filter((t) => user && t.assignee_ids.includes(user.id));
      case "managed":
        return tasks.filter((t) => t.assignee_ids.some((id) => managedUserIds.has(id)));
      case "overdue":
        return tasks.filter(isOverdue);
      case "blocked":
        return tasks.filter((t) => t.status === "blocked");
      case "done":
        return tasks.filter((t) => t.status === "done");
      default:
        return tasks;
    }
  }, [tasks, filter, user, managedUserIds]);

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
    >
      <TouchableOpacity onPress={() => router.push("/projects")} style={{ alignSelf: "flex-end" }}>
        <Text style={{ color: colors.primary, fontWeight: "700" }}>📁 Xem theo Project</Text>
      </TouchableOpacity>
      <View style={styles.filterRow}>
        {FILTERS.map((f) => (
          <TouchableOpacity
            key={f.key}
            style={[styles.chip, filter === f.key && styles.chipActive]}
            onPress={() => setFilter(f.key)}
          >
            <Text style={{ color: filter === f.key ? colors.onPrimary : colors.text }}>
              {f.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
      {tasks === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {filtered?.length === 0 && (
        <Text style={{ color: colors.textMuted }}>Không có task nào ở bộ lọc này</Text>
      )}
      {filtered && filtered.length > 0 && (
        <View style={styles.card}>
          {filtered.map((t) => (
            <TaskRow
              key={t.id}
              t={t}
              projectName={projectNameById.get(t.project_id) ?? "?"}
              assigneeNames={t.assignee_ids.map((id) => userNameById.get(id) ?? "?").join(", ")}
            />
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  filterRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: {
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: radius.md,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
  },
  chipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg },
  row: {
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
});
