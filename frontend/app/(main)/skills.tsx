import React, { useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useRouter } from "expo-router";
import { useAuth } from "../../src/auth/AuthContext";
import {
  Skill,
  SkillDetail,
  SkillKind,
  TaskState,
  addSkillVersion,
  createSkill,
  grantSkill,
  listSkills,
  useSkill,
} from "../../src/api/skills";
import { TaskSummary, listTasks } from "../../src/api/tasks";
import { TeamUser, listUsers } from "../../src/api/team";
import { ErrorText, Field, PrimaryButton } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";

function kindLabel(kind: SkillKind): string {
  return kind === "profile" ? "Hồ sơ năng lực" : "Gói tri thức";
}

// Picker dạng danh sách chọn 1, giống PersonPicker ở team/[id].tsx nhưng tổng quát
// cho mọi nguồn dữ liệu {id, label} — dùng cho cả chọn task lẫn chọn người.
function OptionPicker({
  label,
  options,
  value,
  onChange,
  noneLabel,
}: {
  label: string;
  options: { id: string; label: string }[];
  value: string | null;
  onChange: (id: string | null) => void;
  noneLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const selected = options.find((o) => o.id === value);
  return (
    <View style={{ marginTop: spacing.sm }}>
      <TouchableOpacity onPress={() => setOpen((o) => !o)}>
        <Text style={{ color: colors.primary, fontWeight: "700" }}>
          {label}: {selected ? selected.label : noneLabel ?? "Chưa chọn"}
        </Text>
      </TouchableOpacity>
      {open && (
        <View style={styles.pickerList}>
          {noneLabel && (
            <TouchableOpacity
              onPress={() => {
                onChange(null);
                setOpen(false);
              }}
              style={styles.pickerRow}
            >
              <Text style={{ color: colors.textMuted }}>{noneLabel}</Text>
            </TouchableOpacity>
          )}
          {options.map((o) => (
            <TouchableOpacity
              key={o.id}
              onPress={() => {
                onChange(o.id);
                setOpen(false);
              }}
              style={styles.pickerRow}
            >
              <Text>{o.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
    </View>
  );
}

function TaskStateView({ ts }: { ts: TaskState }) {
  const router = useRouter();
  return (
    <View style={styles.taskStateBox}>
      <TouchableOpacity onPress={() => router.push(`/tasks/${ts.id}`)}>
        <Text style={[styles.cardTitle, { color: colors.primary }]}>{ts.title} →</Text>
      </TouchableOpacity>
      <Text style={{ color: colors.textSecondary }}>
        {ts.status} — {ts.percent}% — Ưu tiên: {ts.priority}
      </Text>
      {ts.deadline && (
        <Text style={{ color: colors.textSecondary }}>
          Deadline: {new Date(ts.deadline).toLocaleDateString("vi-VN")}
        </Text>
      )}
      <Text style={{ color: colors.textSecondary }}>
        Người thực hiện: {ts.assignees.length > 0 ? ts.assignees.join(", ") : "Chưa có"}
      </Text>
      {ts.latest_updates.length === 0 ? (
        <Text style={{ color: colors.textMuted }}>Chưa có cập nhật nào</Text>
      ) : (
        ts.latest_updates.map((u, idx) => (
          <View key={idx} style={styles.updateRow}>
            <Text style={{ color: colors.textSecondary }}>
              {new Date(u.created_at).toLocaleString("vi-VN")}
              {u.percent !== null ? ` — ${u.percent}%` : ""}
            </Text>
            <Text style={type.body}>{u.content}</Text>
          </View>
        ))
      )}
    </View>
  );
}

function SkillCard({
  skill,
  isCeo,
  users,
  usersError,
  usersLoading,
  onRequestUsers,
}: {
  skill: Skill;
  isCeo: boolean;
  users: TeamUser[] | null;
  usersError: string | null;
  usersLoading: boolean;
  onRequestUsers: () => void;
}) {
  const [latestVersion, setLatestVersion] = useState(skill.latest_version);
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState<SkillDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [versionOpen, setVersionOpen] = useState(false);
  const [versionContent, setVersionContent] = useState("");
  const [versionBusy, setVersionBusy] = useState(false);
  const [versionError, setVersionError] = useState<string | null>(null);

  const [grantBusy, setGrantBusy] = useState(false);
  const [grantError, setGrantError] = useState<string | null>(null);
  const [grantSuccess, setGrantSuccess] = useState(false);

  const toggleExpand = () => {
    setExpanded((e) => !e);
    if (!detail && !detailLoading) {
      setDetailLoading(true);
      setDetailError(null);
      useSkill(skill.id)
        .then(setDetail)
        .catch((e: any) => setDetailError(String(e?.message ?? e)))
        .finally(() => setDetailLoading(false));
    }
  };

  const handleSaveVersion = async () => {
    const content = versionContent.trim();
    if (!content) return;
    setVersionBusy(true);
    setVersionError(null);
    try {
      const result = await addSkillVersion(skill.id, content);
      setLatestVersion(result.version);
      setVersionContent("");
      setVersionOpen(false);
      // nội dung đã đổi — bỏ cache để lần mở tiếp theo lấy bản mới nhất
      setDetail(null);
    } catch (e: any) {
      setVersionError(String(e?.message ?? e));
    } finally {
      setVersionBusy(false);
    }
  };

  const handleGrant = async (userId: string | null) => {
    if (!userId) return;
    setGrantBusy(true);
    setGrantError(null);
    setGrantSuccess(false);
    try {
      await grantSkill(skill.id, userId);
      setGrantSuccess(true);
      setTimeout(() => setGrantSuccess(false), 2500);
    } catch (e: any) {
      setGrantError(String(e?.message ?? e));
    } finally {
      setGrantBusy(false);
    }
  };

  return (
    <View style={styles.card}>
      <TouchableOpacity onPress={toggleExpand}>
        <View style={styles.rowHeader}>
          <Text style={styles.cardTitle}>{skill.name}</Text>
          <Text style={{ color: colors.textSecondary }}>v{latestVersion}</Text>
        </View>
        <View style={styles.badgeRow}>
          <View style={styles.badge}>
            <Text style={styles.badgeText}>{kindLabel(skill.kind)}</Text>
          </View>
          {skill.task_id && (
            <View style={styles.badgeOutline}>
              <Text style={styles.badgeOutlineText}>gắn task</Text>
            </View>
          )}
        </View>
      </TouchableOpacity>

      {expanded && (
        <View style={{ marginTop: spacing.sm }}>
          {detailLoading && !detail && <ActivityIndicator color={colors.primary} />}
          <ErrorText error={detailError} />
          {detail && (
            <>
              <Text style={styles.body}>{detail.content}</Text>
              {detail.task_state && <TaskStateView ts={detail.task_state} />}
            </>
          )}

          {isCeo && (
            <View style={{ marginTop: spacing.md }}>
              <TouchableOpacity
                onPress={() => {
                  setVersionOpen((v) => !v);
                  setVersionContent("");
                  setVersionError(null);
                }}
              >
                <Text style={styles.actionText}>+ Phiên bản mới</Text>
              </TouchableOpacity>
              {versionOpen && (
                <View style={{ marginTop: spacing.sm }}>
                  <Field
                    placeholder="Nội dung phiên bản mới..."
                    value={versionContent}
                    onChangeText={setVersionContent}
                    multiline
                  />
                  <ErrorText error={versionError} />
                  <PrimaryButton title="Lưu phiên bản" onPress={handleSaveVersion} busy={versionBusy} />
                </View>
              )}

              <View style={{ marginTop: spacing.md }}>
                {users === null ? (
                  <TouchableOpacity onPress={onRequestUsers} disabled={usersLoading}>
                    {usersLoading ? (
                      <ActivityIndicator color={colors.primary} />
                    ) : (
                      <Text style={styles.actionText}>Cấp quyền</Text>
                    )}
                  </TouchableOpacity>
                ) : (
                  <OptionPicker
                    label="Cấp quyền"
                    options={users.map((u) => ({ id: u.id, label: u.full_name }))}
                    value={null}
                    onChange={handleGrant}
                  />
                )}
                <ErrorText error={usersError} />
                {grantBusy && <ActivityIndicator color={colors.primary} />}
                <ErrorText error={grantError} />
                {grantSuccess && <Text style={styles.successText}>Đã cấp quyền</Text>}
              </View>
            </View>
          )}
        </View>
      )}
    </View>
  );
}

export default function SkillsScreen() {
  const { user } = useAuth();
  const isCeo = user?.role === "ceo";

  const [skills, setSkills] = useState<Skill[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createKind, setCreateKind] = useState<SkillKind>("profile");
  const [createContent, setCreateContent] = useState("");
  const [createTaskId, setCreateTaskId] = useState<string | null>(null);
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [tasks, setTasks] = useState<TaskSummary[] | null>(null);
  const [tasksError, setTasksError] = useState<string | null>(null);
  const [tasksLoading, setTasksLoading] = useState(false);

  const [users, setUsers] = useState<TeamUser[] | null>(null);
  const [usersError, setUsersError] = useState<string | null>(null);
  const [usersLoading, setUsersLoading] = useState(false);

  React.useEffect(() => {
    listSkills()
      .then(setSkills)
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, []);

  const requestTasks = () => {
    if (tasks !== null || tasksLoading) return;
    setTasksLoading(true);
    listTasks()
      .then(setTasks)
      .catch((e: any) => setTasksError(String(e?.message ?? e)))
      .finally(() => setTasksLoading(false));
  };

  const requestUsers = () => {
    if (users !== null || usersLoading) return;
    setUsersLoading(true);
    listUsers()
      .then(setUsers)
      .catch((e: any) => setUsersError(String(e?.message ?? e)))
      .finally(() => setUsersLoading(false));
  };

  const toggleCreate = () => {
    setShowCreate((s) => !s);
    if (!showCreate) requestTasks();
  };

  const submitCreate = async () => {
    const name = createName.trim();
    const content = createContent.trim();
    if (!name || !content) return;
    setCreateBusy(true);
    setCreateError(null);
    try {
      const created = await createSkill({
        name,
        kind: createKind,
        content,
        task_id: createKind === "knowledge" && createTaskId ? createTaskId : undefined,
      });
      setSkills((prev) => (prev ? [created, ...prev] : [created]));
      setCreateName("");
      setCreateContent("");
      setCreateKind("profile");
      setCreateTaskId(null);
      setShowCreate(false);
    } catch (e: any) {
      setCreateError(String(e?.message ?? e));
    } finally {
      setCreateBusy(false);
    }
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
    >
      {skills === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />

      {isCeo && (
        <View style={styles.card}>
          <TouchableOpacity onPress={toggleCreate}>
            <Text style={styles.actionText}>{showCreate ? "Đóng" : "+ Tạo skill"}</Text>
          </TouchableOpacity>
          {showCreate && (
            <View style={{ marginTop: spacing.sm }}>
              <Field placeholder="Tên skill" value={createName} onChangeText={setCreateName} />
              <View style={{ flexDirection: "row", gap: spacing.sm, marginBottom: spacing.md }}>
                <TouchableOpacity
                  style={[styles.chip, createKind === "profile" && styles.chipActive]}
                  onPress={() => setCreateKind("profile")}
                >
                  <Text style={{ color: createKind === "profile" ? colors.onPrimary : colors.text }}>
                    Hồ sơ năng lực
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.chip, createKind === "knowledge" && styles.chipActive]}
                  onPress={() => setCreateKind("knowledge")}
                >
                  <Text style={{ color: createKind === "knowledge" ? colors.onPrimary : colors.text }}>
                    Gói tri thức
                  </Text>
                </TouchableOpacity>
              </View>
              <Field
                placeholder="Nội dung..."
                value={createContent}
                onChangeText={setCreateContent}
                multiline
              />
              {createKind === "knowledge" && (
                <>
                  {tasksLoading && <ActivityIndicator color={colors.primary} />}
                  <ErrorText error={tasksError} />
                  <OptionPicker
                    label="Task liên kết"
                    options={(tasks ?? []).map((t) => ({ id: t.id, label: t.title }))}
                    value={createTaskId}
                    onChange={setCreateTaskId}
                    noneLabel="Không gắn task"
                  />
                </>
              )}
              <ErrorText error={createError} />
              <PrimaryButton title="Tạo" onPress={submitCreate} busy={createBusy} />
            </View>
          )}
        </View>
      )}

      {skills?.length === 0 && <Text style={{ color: colors.textMuted }}>Chưa có skill nào</Text>}

      {skills?.map((s) => (
        <SkillCard
          key={s.id}
          skill={s}
          isCeo={isCeo}
          users={users}
          usersError={usersError}
          usersLoading={usersLoading}
          onRequestUsers={requestUsers}
        />
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm },
  cardTitle: { ...type.heading },
  actionText: { color: colors.primary, fontWeight: "700" },
  successText: { color: colors.success },
  rowHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  badgeRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs },
  badge: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  badgeText: { color: colors.textSecondary, fontSize: type.caption.fontSize, fontWeight: "700" },
  badgeOutline: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  badgeOutlineText: { color: colors.textMuted, fontSize: type.caption.fontSize },
  body: { ...type.body, marginTop: spacing.sm },
  taskStateBox: {
    marginTop: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.bg,
    borderWidth: 1,
    borderColor: colors.divider,
    gap: spacing.xs,
  },
  updateRow: {
    paddingTop: spacing.xs,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
  chip: {
    borderWidth: 1,
    borderColor: colors.borderStrong,
    borderRadius: radius.md,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
  },
  chipActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  pickerList: {
    marginTop: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
  },
  pickerRow: {
    padding: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
  },
});
