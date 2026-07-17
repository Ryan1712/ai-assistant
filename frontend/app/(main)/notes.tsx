import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { Note, createNote, listNotes } from "../../src/api/notes";
import { Field, PrimaryButton, ErrorText } from "../../src/ui/form";
import { colors, radius, spacing, type } from "../../src/ui/theme";

function todayIso(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function NoteRow({ note }: { note: Note }) {
  return (
    <View style={styles.row}>
      <Text style={type.body}>{note.content}</Text>
      {note.tags.length > 0 && (
        <Text style={styles.meta}>{note.tags.map((t) => `#${t}`).join(" · ")}</Text>
      )}
      <Text style={styles.meta}>{new Date(note.note_date).toLocaleDateString("vi-VN")}</Text>
    </View>
  );
}

export default function NotesScreen() {
  const [filter, setFilter] = useState<"today" | "all">("today");
  const [tagInput, setTagInput] = useState("");
  const [tagFilter, setTagFilter] = useState<string | undefined>(undefined);
  const [notes, setNotes] = useState<Note[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [content, setContent] = useState("");
  const [tagsText, setTagsText] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    setNotes(null);
    listNotes({ onDate: filter === "today" ? todayIso() : undefined, tag: tagFilter })
      .then(setNotes)
      .catch((e: any) => setError(String(e?.message ?? e)));
  }, [filter, tagFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const handleFilterTag = () => {
    setTagFilter(tagInput.trim() || undefined);
  };

  const handleCreate = async () => {
    if (!content.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      const tags = tagsText
        .split(",")
        .map((t) => t.trim())
        .filter((t) => t.length > 0);
      const created = await createNote({
        content: content.trim(),
        tags: tags.length > 0 ? tags : undefined,
        note_date: todayIso(),
      });
      setContent("");
      setTagsText("");
      // Chỉ thêm vào danh sách đang hiển thị nếu khớp bộ lọc tag hiện tại —
      // BE trả list mới nhất trước nên thêm lên đầu để khớp thứ tự.
      if (!tagFilter || created.tags.includes(tagFilter)) {
        setNotes((prev) => (prev ? [created, ...prev] : [created]));
      }
    } catch (e: any) {
      setCreateError(String(e?.message ?? e));
    } finally {
      setCreating(false);
    }
  };

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg }}
      contentContainerStyle={{ padding: spacing.md, gap: spacing.md }}
    >
      <View style={styles.card}>
        <View style={styles.filterRow}>
          <TouchableOpacity onPress={() => setFilter("today")}>
            <Text style={filter === "today" ? styles.chipActive : styles.chipInactive}>
              Hôm nay
            </Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setFilter("all")}>
            <Text style={filter === "all" ? styles.chipActive : styles.chipInactive}>
              Tất cả
            </Text>
          </TouchableOpacity>
        </View>
        <View style={styles.tagFilterRow}>
          <Field
            style={styles.tagField}
            placeholder="Lọc theo tag..."
            value={tagInput}
            onChangeText={setTagInput}
          />
          <TouchableOpacity onPress={handleFilterTag} style={styles.filterButton}>
            <Text style={{ color: colors.primary, fontWeight: "700" }}>Lọc</Text>
          </TouchableOpacity>
        </View>
      </View>

      {notes === null && !error && (
        <ActivityIndicator color={colors.primary} style={{ marginTop: spacing.xxl }} />
      )}
      <ErrorText error={error} />
      {notes?.length === 0 && (
        <Text style={{ color: colors.textMuted }}>Chưa có ghi chú nào</Text>
      )}
      {notes && notes.length > 0 && (
        <View style={styles.card}>
          {notes.map((n) => (
            <NoteRow key={n.id} note={n} />
          ))}
        </View>
      )}

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Ghi chú mới</Text>
        <Field
          placeholder="Nội dung ghi chú..."
          value={content}
          onChangeText={setContent}
          multiline
          style={styles.contentField}
        />
        <Field
          placeholder="Tag, phân cách bằng dấu phẩy"
          value={tagsText}
          onChangeText={setTagsText}
        />
        <ErrorText error={createError} />
        <PrimaryButton title="Lưu ghi chú" onPress={handleCreate} busy={creating} />
      </View>
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
  filterRow: { flexDirection: "row", gap: spacing.lg },
  chipActive: { color: colors.primary, fontWeight: "700" },
  chipInactive: { color: colors.textSecondary, fontWeight: "400" },
  tagFilterRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  tagField: { flex: 1, marginBottom: 0 },
  filterButton: { paddingHorizontal: spacing.sm, paddingVertical: spacing.sm },
  contentField: { minHeight: 80, textAlignVertical: "top" },
  row: {
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderColor: colors.divider,
    gap: spacing.xs,
  },
  meta: { color: colors.textSecondary, fontSize: type.caption.fontSize },
});
