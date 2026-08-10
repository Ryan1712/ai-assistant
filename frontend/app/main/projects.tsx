import React, { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, ScrollView, Text, View } from "react-native";
import { Project, listProjects } from "../../src/api/projects";
import { TaskDetail, listTasks } from "../../src/api/tasks";
import { BackHeader } from "../../src/ui/BackHeader";
import { ErrorText } from "../../src/ui/form";
import { colors, spacing } from "../../src/ui/theme";
import { ProjectCard } from "./ProjectCard";

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
