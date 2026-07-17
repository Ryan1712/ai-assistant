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
import {
  Instruction,
  createInstruction,
  deleteInstruction,
  listInstructions,
  updateInstruction,
} from "../../src/api/instructions";
import { ErrorText, Field, PrimaryButton } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";

function InstructionRow({
  ins,
  onUpdated,
  onDeleted,
  onError,
}: {
  ins: Instruction;
  onUpdated: (id: string, content: string, version: number) => void;
  onDeleted: (id: string) => void;
  onError: (msg: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(ins.content);
  const [busy, setBusy] = useState(false);

  const startEdit = () => {
    setDraft(ins.content);
    setEditing(true);
  };

  const save = async () => {
    setBusy(true);
    try {
      const res = await updateInstruction(ins.id, draft);
      onUpdated(ins.id, draft, res.version);
      setEditing(false);
    } catch (e: any) {
      onError(String(e?.message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const confirmDelete = () => {
    Alert.alert("Xóa chỉ dẫn?", `"${ins.title}" sẽ không còn được AI áp dụng nữa.`, [
      { text: "Hủy", style: "cancel" },
      {
        text: "Xóa",
        style: "destructive",
        onPress: async () => {
          try {
            await deleteInstruction(ins.id);
            onDeleted(ins.id);
          } catch (e: any) {
            onError(String(e?.message ?? e));
          }
        },
      },
    ]);
  };

  return (
    <View style={styles.row}>
      <View style={styles.rowHeader}>
        <Text style={type.heading}>{ins.title}</Text>
        <View style={styles.badge}>
          <Text style={styles.badgeText}>v{ins.version}</Text>
        </View>
      </View>
      {editing ? (
        <>
          <Field value={draft} onChangeText={setDraft} multiline textAlignVertical="top" />
          <View style={styles.actionsRow}>
            <TouchableOpacity onPress={() => setEditing(false)} disabled={busy}>
              <Text style={{ color: colors.textSecondary, fontWeight: "700" }}>Hủy</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={save} disabled={busy}>
              {busy ? (
                <ActivityIndicator color={colors.primary} />
              ) : (
                <Text style={{ color: colors.primary, fontWeight: "700" }}>Lưu</Text>
              )}
            </TouchableOpacity>
          </View>
        </>
      ) : (
        <>
          <Text style={type.body}>{ins.content}</Text>
          <View style={styles.actionsRow}>
            <TouchableOpacity onPress={startEdit}>
              <Text style={{ color: colors.primary, fontWeight: "700" }}>Sửa</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={confirmDelete}>
              <Text style={{ color: colors.danger, fontWeight: "700" }}>Xóa</Text>
            </TouchableOpacity>
          </View>
        </>
      )}
    </View>
  );
}

export default function Instructions() {
  const [instructions, setInstructions] = useState<Instruction[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    listInstructions()
      .then(setInstructions)
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, []);

  const submit = async () => {
    if (!title.trim() || !content.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const created = await createInstruction({ title: title.trim(), content: content.trim() });
      setInstructions((prev) => (prev ? [created, ...prev] : [created]));
      setTitle("");
      setContent("");
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setCreating(false);
    }
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
    >
      <Text style={{ ...type.caption, color: colors.textSecondary }}>
        Chỉ dẫn cho AI — quy tắc/bối cảnh bạn cấu hình, AI nạp lại ngay khi có thay đổi.
      </Text>

      {instructions === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {instructions?.length === 0 && (
        <Text style={{ color: colors.textMuted }}>Chưa có chỉ dẫn nào</Text>
      )}
      {instructions && instructions.length > 0 && (
        <View style={styles.card}>
          {instructions.map((ins) => (
            <InstructionRow
              key={ins.id}
              ins={ins}
              onUpdated={(id, newContent, version) =>
                setInstructions((prev) =>
                  prev
                    ? prev.map((x) => (x.id === id ? { ...x, content: newContent, version } : x))
                    : prev,
                )
              }
              onDeleted={(id) =>
                setInstructions((prev) => (prev ? prev.filter((x) => x.id !== id) : prev))
              }
              onError={setError}
            />
          ))}
        </View>
      )}

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Thêm chỉ dẫn mới</Text>
        <Field placeholder="Tiêu đề" value={title} onChangeText={setTitle} autoCapitalize="sentences" />
        <Field
          placeholder="Nội dung chỉ dẫn"
          value={content}
          onChangeText={setContent}
          multiline
          textAlignVertical="top"
          autoCapitalize="sentences"
        />
        <PrimaryButton title="Thêm chỉ dẫn" onPress={submit} busy={creating} />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm },
  cardTitle: { ...type.heading },
  row: {
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
    gap: spacing.sm,
  },
  rowHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    gap: spacing.sm,
  },
  badge: {
    backgroundColor: colors.surfaceAlt,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
  },
  badgeText: { ...type.caption, fontWeight: "700" },
  actionsRow: { flexDirection: "row", gap: spacing.lg },
});
